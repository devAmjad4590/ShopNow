# Run: pip install -r requirements.txt
# Then: pytest -v

import os
import uuid

import httpx
import pytest

# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------

# All gateway-routed tests target this URL. Override with GATEWAY_URL env var.
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")

# Direct service URL kept for the product-catalog smoke tests that were written
# before the gateway was wired up for those routes.
CATALOG_DIRECT_URL = os.environ.get("CATALOG_URL", "http://localhost:8083/api/v1")


@pytest.fixture(scope="session")
def base_url() -> str:
    """Direct URL for the product-catalog service (used by test_categories.py)."""
    return CATALOG_DIRECT_URL


@pytest.fixture(scope="session")
def gateway_url() -> str:
    """Root URL for the API Gateway. Auth tests target this."""
    return GATEWAY_URL


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def registered_user(gateway_url: str) -> dict:
    """
    Registers a brand-new user via the API Gateway and returns the payload
    that was used so downstream fixtures can log in with it.

    Uses a UUID-derived email to guarantee uniqueness across test runs.
    """
    unique_id = uuid.uuid4().hex[:12]
    payload = {
        "firstName": "Test",
        "lastName": "User",
        "email": f"test.{unique_id}@shopnow-test.com",
        "password": "SecurePass1!",
    }

    response = httpx.post(f"{gateway_url}/auth/register", json=payload)
    assert response.status_code == 200, (
        f"Registration fixture failed ({response.status_code}): {response.text}"
    )

    # Return the credentials so login fixtures can reuse them.
    return payload


@pytest.fixture(scope="session")
def auth_tokens(gateway_url: str, registered_user: dict) -> dict:
    """
    Logs in the registered_user and returns:
      {
        "access_token":   "<jwt>",
        "refresh_token":  "<token from Set-Cookie>",
      }
    Scoped to session so we only log in once for the entire test run.
    """
    response = httpx.post(
        f"{gateway_url}/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert response.status_code == 200, (
        f"Login fixture failed ({response.status_code}): {response.text}"
    )

    body = response.json()
    access_token = body.get("access_token")
    assert access_token, f"access_token missing from login response: {body}"

    # The refresh token is delivered via HttpOnly Set-Cookie, not the response body.
    set_cookie = response.headers.get("set-cookie", "")
    refresh_token = None
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith("refresh_token="):
            refresh_token = part[len("refresh_token="):]
            break

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
