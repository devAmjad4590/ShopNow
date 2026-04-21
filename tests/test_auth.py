# Auth Service — integration tests
#
# All requests are sent to the API Gateway (port 8080) which routes:
#   /auth/**  →  PrefixPath=/api/v1  →  auth-service at localhost:8081
# so the effective upstream path is /api/v1/auth/*.
#
# Run: pytest tests/test_auth.py -v
#
# Prerequisites: full stack must be running (gateway + auth-service + postgres).

import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_email() -> str:
    return f"test.{uuid.uuid4().hex[:10]}@shopnow-test.com"


def _register(gateway_url: str, **overrides) -> httpx.Response:
    """POST /auth/register with sensible defaults, any field overridable."""
    payload = {
        "firstName": "Alice",
        "lastName": "Smith",
        "email": _unique_email(),
        "password": "ValidPass1!",
    }
    payload.update(overrides)
    return httpx.post(f"{gateway_url}/auth/register", json=payload)


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

class TestRegister:
    """Tests for POST /auth/register via the API Gateway."""

    def test_happy_path_returns_200_and_success_message(self, gateway_url: str) -> None:
        """
        A valid registration payload should return HTTP 200 with a JSON body
        that contains a non-empty 'message' field.
        """
        response = _register(gateway_url)

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "message" in body, f"'message' key missing from response: {body}"
        assert body["message"], "'message' field is empty"

    def test_duplicate_email_rejected(self, gateway_url: str) -> None:
        """
        Registering the same email address twice must be rejected.
        No @ControllerAdvice handles DataIntegrityViolationException in the auth-service
        yet, so we assert >= 400 rather than a specific 409.
        TODO: tighten to 409 once a global exception handler is added.
        """
        email = _unique_email()
        _register(gateway_url, email=email)           # first registration — must succeed
        response = _register(gateway_url, email=email) # second — must fail

        assert response.status_code >= 400, (
            f"Expected an error status for duplicate email but got {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("missing_field", ["firstName", "lastName", "email", "password"])
    def test_missing_required_field_returns_400(self, gateway_url: str, missing_field: str) -> None:
        """
        Each required field is individually omitted. Spring's @Valid annotation
        should reject the request with HTTP 400.
        """
        payload = {
            "firstName": "Bob",
            "lastName": "Jones",
            "email": _unique_email(),
            "password": "ValidPass1!",
        }
        del payload[missing_field]

        response = httpx.post(f"{gateway_url}/auth/register", json=payload)

        assert response.status_code == 400, (
            f"Expected 400 when '{missing_field}' is absent, got {response.status_code}: {response.text}"
        )

    def test_invalid_email_format_returns_400(self, gateway_url: str) -> None:
        """
        An email string that fails the @Email constraint should return 400.
        """
        response = _register(gateway_url, email="not-an-email")

        assert response.status_code == 400, (
            f"Expected 400 for malformed email, got {response.status_code}: {response.text}"
        )

    def test_password_too_short_returns_400(self, gateway_url: str) -> None:
        """
        Passwords shorter than 8 characters violate the @Size(min=8) constraint
        and should return 400.
        """
        response = _register(gateway_url, password="Short1!")

        assert response.status_code == 400, (
            f"Expected 400 for short password, got {response.status_code}: {response.text}"
        )

    def test_empty_body_returns_400(self, gateway_url: str) -> None:
        """An empty JSON object should fail all @NotBlank constraints → 400."""
        response = httpx.post(
            f"{gateway_url}/auth/register",
            json={},
        )
        assert response.status_code == 400, (
            f"Expected 400 for empty body, got {response.status_code}: {response.text}"
        )

    def test_blank_first_name_returns_400(self, gateway_url: str) -> None:
        """A whitespace-only firstName violates @NotBlank and should return 400."""
        response = _register(gateway_url, firstName="   ")

        assert response.status_code == 400, (
            f"Expected 400 for blank firstName, got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

class TestLogin:
    """Tests for POST /auth/login via the API Gateway."""

    def test_happy_path_returns_200_access_token_and_refresh_cookie(
        self, gateway_url: str, registered_user: dict
    ) -> None:
        """
        Valid credentials should return:
          - HTTP 200
          - JSON body with 'access_token' (refresh_token is nulled out in the body)
          - Set-Cookie header containing 'refresh_token' (HttpOnly, path=/auth)
        """
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )

        body = response.json()
        assert "access_token" in body, f"'access_token' missing from login response: {body}"
        assert body["access_token"], "'access_token' is empty"

        # refresh_token must NOT appear in the body — it is delivered via cookie only
        assert "refresh_token" not in body or body.get("refresh_token") is None, (
            "refresh_token must not appear in the login response body"
        )

        # The Set-Cookie header must carry the refresh token
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie, (
            f"Expected 'refresh_token' cookie in Set-Cookie, got: {set_cookie!r}"
        )
        assert "HttpOnly" in set_cookie, "refresh_token cookie must be HttpOnly"

    def test_wrong_password_returns_401(self, gateway_url: str, registered_user: dict) -> None:
        """
        Correct email with the wrong password must be rejected with 401.
        Spring Security's AuthenticationManager raises BadCredentialsException
        which results in a 401 Unauthorized response.
        """
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": registered_user["email"],
                "password": "WrongPassword999!",
            },
        )

        assert response.status_code == 401, (
            f"Expected 401 for wrong password but got {response.status_code}: {response.text}"
        )

    def test_nonexistent_email_returns_401(self, gateway_url: str) -> None:
        """
        Attempting to log in with an email that was never registered should
        return 401 (Spring Security treats user-not-found as a credentials failure).
        """
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": "ghost.user.nobody@shopnow-test.com",
                "password": "ValidPass1!",
            },
        )

        assert response.status_code == 401, (
            f"Expected 401 for unknown email but got {response.status_code}: {response.text}"
        )

    def test_missing_email_returns_400(self, gateway_url: str) -> None:
        """Omitting 'email' violates @NotBlank → 400."""
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={"password": "ValidPass1!"},
        )
        assert response.status_code == 400, (
            f"Expected 400 when email is missing, got {response.status_code}: {response.text}"
        )

    def test_missing_password_returns_400(self, gateway_url: str) -> None:
        """Omitting 'password' violates @NotBlank → 400."""
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={"email": "someone@shopnow-test.com"},
        )
        assert response.status_code == 400, (
            f"Expected 400 when password is missing, got {response.status_code}: {response.text}"
        )

    def test_invalid_email_format_returns_400(self, gateway_url: str) -> None:
        """A malformed email string violates @Email → 400."""
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={"email": "not-valid", "password": "ValidPass1!"},
        )
        assert response.status_code == 400, (
            f"Expected 400 for malformed email, got {response.status_code}: {response.text}"
        )

    def test_empty_body_returns_400(self, gateway_url: str) -> None:
        """An empty JSON object should fail all @NotBlank constraints → 400."""
        response = httpx.post(f"{gateway_url}/auth/login", json={})
        assert response.status_code == 400, (
            f"Expected 400 for empty body, got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    """Tests for POST /auth/refresh via the API Gateway.

    The controller reads the refresh token from the 'refresh_token' HttpOnly cookie,
    not from the request body.  Missing cookie → 403 (returned directly by the
    controller, not Spring Security).  Invalid token → 500 currently (no
    @ControllerAdvice maps the RuntimeException to a client error yet).
    """

    def test_happy_path_returns_200_and_rotates_tokens(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        A valid refresh_token cookie must return:
          - HTTP 200
          - JSON body with 'accessToken' (camelCase, matching RefreshResponse)
          - A new 'refresh_token' Set-Cookie header (token rotation)
        """
        refresh_token = auth_tokens["refresh_token"]
        assert refresh_token, "auth_tokens fixture did not capture a refresh_token"

        response = httpx.post(
            f"{gateway_url}/auth/refresh",
            cookies={"refresh_token": refresh_token},
        )

        assert response.status_code == 200, (
            f"Expected 200 for valid refresh token, got {response.status_code}: {response.text}"
        )

        body = response.json()
        # RefreshResponse uses camelCase: accessToken / refreshToken
        assert "accessToken" in body, f"'accessToken' missing from refresh response: {body}"
        assert body["accessToken"], "'accessToken' is empty"

        # Rotated refresh token must come back via Set-Cookie
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie, (
            f"Expected a new 'refresh_token' cookie in Set-Cookie, got: {set_cookie!r}"
        )

    def test_new_access_token_differs_from_old(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        The refreshed access token must be a different string from the original.
        This guards against token rotation being a no-op.
        """
        refresh_token = auth_tokens["refresh_token"]
        original_access_token = auth_tokens["access_token"]

        response = httpx.post(
            f"{gateway_url}/auth/refresh",
            cookies={"refresh_token": refresh_token},
        )

        assert response.status_code == 200, (
            f"Refresh failed ({response.status_code}): {response.text}"
        )
        new_access_token = response.json().get("accessToken")
        assert new_access_token != original_access_token, (
            "Refreshed access token must not be identical to the original"
        )

    def test_missing_cookie_returns_403(self, gateway_url: str) -> None:
        """
        The controller explicitly checks for a null cookie value and returns
        HTTP 403 Forbidden when the refresh_token cookie is absent.
        """
        response = httpx.post(f"{gateway_url}/auth/refresh")

        assert response.status_code == 403, (
            f"Expected 403 when refresh_token cookie is absent, got {response.status_code}: {response.text}"
        )

    def test_tampered_token_returns_error(self, gateway_url: str) -> None:
        """
        A syntactically plausible but cryptographically invalid token must be
        rejected.  The auth-service currently has no @ControllerAdvice for the
        resulting RuntimeException, so the response will be a 5xx.
        TODO: add a @ControllerAdvice that maps invalid-token errors to 401.
        """
        tampered = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlQHVzZXIuY29tIn0.invalidsignature"
        response = httpx.post(
            f"{gateway_url}/auth/refresh",
            cookies={"refresh_token": tampered},
        )

        assert response.status_code >= 400, (
            f"Expected an error response for a tampered token, got {response.status_code}: {response.text}"
        )

    def test_empty_string_cookie_returns_error(self, gateway_url: str) -> None:
        """
        An empty string as the cookie value is structurally invalid.
        The controller treats it as non-null (cookie is present but value is ''),
        so the service layer will raise an exception when parsing the JWT.
        Expect any 4xx or 5xx.
        """
        response = httpx.post(
            f"{gateway_url}/auth/refresh",
            cookies={"refresh_token": ""},
        )

        # Empty string: the @CookieValue 'required=false' will still receive the value,
        # but JWTService.extractUsername will fail.
        assert response.status_code >= 400, (
            f"Expected error for empty cookie value, got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: response shape contracts
# ---------------------------------------------------------------------------

class TestResponseShape:
    """
    Lightweight contract tests: assert on the JSON field names that the
    caller must rely on.  These catch renames / serialisation changes early.
    """

    def test_login_response_has_message_and_access_token(
        self, gateway_url: str, registered_user: dict
    ) -> None:
        """LoginResponse must expose 'message' and 'access_token' (snake_case)."""
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"message", "access_token"}, (
            f"Unexpected shape for LoginResponse: {list(body.keys())}"
        )

    def test_register_response_has_message(self, gateway_url: str) -> None:
        """RegistrationResponse must expose a 'message' field."""
        response = _register(gateway_url)
        assert response.status_code == 200
        body = response.json()
        assert "message" in body, f"'message' missing from RegistrationResponse: {body}"

    def test_refresh_response_uses_camel_case(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """RefreshResponse must use camelCase 'accessToken', not 'access_token'."""
        response = httpx.post(
            f"{gateway_url}/auth/refresh",
            cookies={"refresh_token": auth_tokens["refresh_token"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert "accessToken" in body, (
            f"Expected camelCase 'accessToken' in RefreshResponse, got keys: {list(body.keys())}"
        )
        assert "access_token" not in body, (
            "RefreshResponse must not contain snake_case 'access_token' — use 'accessToken'"
        )
