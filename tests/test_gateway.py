# API Gateway — cross-cutting integration tests
#
# These tests exercise gateway-level concerns only:
#   - Route forwarding: does each configured path prefix reach the right service?
#   - JWT filter: does the global filter enforce auth correctly?
#   - Public routes: /auth/** must be reachable without any token.
#   - Unknown routes: unmapped paths must return 404 from the gateway itself.
#
# All requests target the API Gateway on port 8080 (GATEWAY_URL env var).
# Individual service ports are never contacted directly in this file.
#
# Run:
#   pytest tests/test_gateway.py -v
#   GATEWAY_URL=http://staging:8080 pytest tests/test_gateway.py -v

import httpx
import pytest

# ---------------------------------------------------------------------------
# Marker: xfail used below only if a specific gateway feature is a stub.
# As of the current codebase, JWTAuthenticationFilter IS fully implemented,
# so no xfail markers are needed for the JWT tests in this file.
# ---------------------------------------------------------------------------


# ===========================================================================
# Section 1 – Public route accessibility (/auth/**)
#
# The JWT filter explicitly bypasses /auth/** paths.
# These tests confirm that unauthenticated callers can reach the Auth Service
# through the gateway without providing any token.
# ===========================================================================

class TestPublicAuthRoutes:
    """Routes under /auth/ must be reachable without a Bearer token."""

    def test_register_is_reachable_without_token(self, gateway_url: str) -> None:
        """POST /auth/register with a valid payload returns 200 — no token needed.

        If the gateway JWT filter incorrectly intercepts /auth/ paths, this
        will return 401 instead of 200.
        """
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        response = httpx.post(
            f"{gateway_url}/auth/register",
            json={
                "firstName": "Public",
                "lastName": "Route",
                "email": f"public-route-{unique_id}@shopnow-test.com",
                "password": "PublicRoute1!",
            },
            timeout=10,
        )
        # 200 = register succeeded and route is reachable
        # 409 = conflict (duplicate email) — still reachable, not a 401
        assert response.status_code in (200, 409), (
            f"Expected 200 or 409 (route is public), got {response.status_code}: "
            f"{response.text}"
        )

    def test_login_is_reachable_without_token(
        self, gateway_url: str, registered_user: dict
    ) -> None:
        """POST /auth/login with valid credentials returns 200 — no token needed.

        Confirms that the gateway does not block the login endpoint, which
        would make it impossible for any user to ever obtain a token.
        """
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
            timeout=10,
        )
        assert response.status_code == 200, (
            f"Login should be public (no token required), got "
            f"{response.status_code}: {response.text}"
        )

    def test_login_response_contains_access_token(
        self, gateway_url: str, registered_user: dict
    ) -> None:
        """The login response body must contain access_token.

        Validates that the gateway did not strip or transform the downstream
        auth service response body.
        """
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
            timeout=10,
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body, (
            f"access_token missing from gateway-proxied login response: {body}"
        )
        assert body["access_token"], "access_token must be a non-empty string"

    def test_login_sets_refresh_token_cookie(
        self, gateway_url: str, registered_user: dict
    ) -> None:
        """The gateway must forward the Set-Cookie header from the auth service.

        The auth service sets an HttpOnly cookie named 'refresh_token'.
        If the gateway strips Set-Cookie headers, refresh flows will silently
        break for every client.
        """
        response = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
            timeout=10,
        )
        assert response.status_code == 200
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie_header, (
            "Expected a Set-Cookie header containing 'refresh_token=' but got: "
            f"{set_cookie_header!r}"
        )


# ===========================================================================
# Section 2 – JWT filter: missing / malformed / expired tokens
#
# The JWT filter (JWTAuthenticationFilter) runs on every request that is NOT
# under /auth/**.  It must return 401 for any request that lacks a valid token.
# ===========================================================================

class TestJWTFilterRejectsInvalidRequests:
    """Protected routes must return 401 when the token is absent or invalid."""

    def test_no_token_on_protected_route_returns_401(
        self, gateway_url: str
    ) -> None:
        """GET /users/me/profile without Authorization header → 401.

        The gateway JWT filter checks for a Bearer token before forwarding.
        No token must never reach the downstream user service.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            timeout=10,
        )
        assert response.status_code == 401, (
            f"Expected 401 (no token), got {response.status_code}: {response.text}"
        )

    def test_malformed_bearer_token_returns_401(self, gateway_url: str) -> None:
        """Authorization: Bearer <garbage> → 401.

        A token that is not a valid JWT (wrong format, bad base64) must be
        rejected by the gateway before the request reaches any downstream service.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
            timeout=10,
        )
        assert response.status_code == 401, (
            f"Expected 401 (malformed token), got {response.status_code}: "
            f"{response.text}"
        )

    def test_wrong_scheme_returns_401(self, gateway_url: str) -> None:
        """Authorization: Basic <token> → 401.

        The filter explicitly requires the 'Bearer ' prefix.  A Basic auth
        header must not satisfy the check.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
            timeout=10,
        )
        assert response.status_code == 401, (
            f"Expected 401 (wrong scheme), got {response.status_code}: "
            f"{response.text}"
        )

    def test_empty_bearer_value_returns_401(self, gateway_url: str) -> None:
        """Authorization: Bearer  (just a space, no token) → 401.

        After stripping the 'Bearer ' prefix the remaining string is empty;
        JJWT will throw a parsing exception so isTokenValid returns false.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": "Bearer "},
            timeout=10,
        )
        assert response.status_code == 401, (
            f"Expected 401 (empty bearer value), got {response.status_code}: "
            f"{response.text}"
        )

    def test_expired_token_returns_401(self, gateway_url: str) -> None:
        """Authorization: Bearer <expired JWT> → 401.

        This token was signed with a valid secret but has exp set in the past.
        The gateway must check expiry and reject it, not forward to the service.

        The token below is a structurally valid HS256 JWT with:
          sub=1, userId=1, role=USER
          iat=1609459200 (2021-01-01), exp=1609459200 (already expired)
        It was signed with the key "dGVzdHNlY3JldGtleWZvcnRlc3Rpbmc=" which
        is unlikely to be the production secret, so JJWT will throw a
        SignatureException — also caught by isTokenValid → returns false → 401.
        Either expiry or signature mismatch correctly produces 401 here.
        """
        expired_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxIiwidXNlcklkIjoxLCJyb2xlIjoiVVNFUiIsImlhdCI6MTYwOTQ1OTIwMCwiZXhwIjoxNjA5NDU5MjAwfQ"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": f"Bearer {expired_token}"},
            timeout=10,
        )
        assert response.status_code == 401, (
            f"Expected 401 (expired token), got {response.status_code}: "
            f"{response.text}"
        )


# ===========================================================================
# Section 3 – JWT filter: valid token is forwarded
#
# A request with a genuine token (obtained from the auth service) must pass
# through the filter, reach the downstream service, and return a non-401.
# ===========================================================================

class TestJWTFilterForwardsValidToken:
    """Protected routes must be reachable with a valid token."""

    def test_valid_token_reaches_user_service(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """GET /users/me/profile with a valid token must NOT return 401.

        The expected status is 200 (profile exists — created by the
        registered_user fixture) or 404 (profile not created yet for the
        test user).  Either is acceptable here because we are testing the
        gateway layer, not the user service business logic.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            timeout=10,
        )
        assert response.status_code != 401, (
            f"A valid token should not return 401 from the gateway filter. "
            f"Got {response.status_code}: {response.text}"
        )
        assert response.status_code != 403, (
            f"A valid token should not return 403 from the gateway filter. "
            f"Got {response.status_code}: {response.text}"
        )

    def test_gateway_injects_x_user_id_header(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """The gateway must inject X-User-Id when a valid token is presented.

        The user service reads identity from the X-User-Id header set by the
        gateway (not from the JWT itself), so a missing header would cause
        profile lookups to fail silently or with 500.

        We verify this indirectly: if the user service returns a meaningful
        response (200 or 404 with a body) rather than an internal error,
        the header was injected correctly.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            timeout=10,
        )
        # 500 would indicate the downstream service could not read X-User-Id
        assert response.status_code != 500, (
            f"Got 500 — likely X-User-Id header was not injected by the gateway. "
            f"Response: {response.text}"
        )


# ===========================================================================
# Section 4 – Route forwarding smoke tests
#
# Each configured gateway route is exercised with a lightweight request to
# confirm the gateway correctly proxies to the right downstream service.
# We use endpoints that are safe to call without side effects (GET requests,
# or the register endpoint which handles duplicates gracefully).
#
# Gateway route table (from application.yml):
#   /auth/**        → http://localhost:8081  (PrefixPath=/api/v1)
#   /users/**       → http://localhost:8082  (PrefixPath=/api/v1)
#   /products/**    → http://localhost:8083  (PrefixPath=/api/v1)
#   /categories/**  → http://localhost:8083  (PrefixPath=/api/v1)
# ===========================================================================

class TestRouteForwarding:
    """Each route prefix must be proxied to the correct downstream service."""

    def test_auth_route_reaches_auth_service(self, gateway_url: str) -> None:
        """/auth/register must be forwarded to the auth service (port 8081).

        A 400 or 422 from the auth service is fine — it means the request
        arrived and was validated. A 502/503/504 means the gateway could not
        reach the downstream service (network/routing issue).
        """
        response = httpx.post(
            f"{gateway_url}/auth/register",
            json={},  # deliberately empty → expect 400 from auth service
            timeout=10,
        )
        # Any 4xx from the downstream service confirms routing works.
        # 502/503/504 = gateway-level routing failure.
        assert response.status_code < 500, (
            f"Gateway failed to route /auth/** to the auth service. "
            f"Got {response.status_code}: {response.text}"
        )
        assert response.status_code != 404, (
            "Got 404 — the /auth/** route is not configured in the gateway or "
            "the auth service does not have a matching endpoint."
        )

    def test_products_route_reaches_product_catalog(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """/products/ must be forwarded to the product-catalog service (port 8083).

        Uses a valid token because the gateway JWT filter will reject the
        request before forwarding if no token is provided.
        A 200 (empty list), 404, or similar 4xx from the catalog service
        confirms the route is correctly wired.
        """
        response = httpx.get(
            f"{gateway_url}/products/",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            timeout=10,
        )
        assert response.status_code < 500, (
            f"Gateway failed to route /products/** to the product-catalog service. "
            f"Got {response.status_code}: {response.text}"
        )

    def test_categories_route_reaches_product_catalog(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """/categories/ must be forwarded to the product-catalog service (port 8083).

        Categories share the same downstream service as products.  This test
        confirms that the compound predicate (Path=/products/**, /categories/**)
        correctly routes both prefixes.
        """
        response = httpx.get(
            f"{gateway_url}/categories/",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            timeout=10,
        )
        assert response.status_code < 500, (
            f"Gateway failed to route /categories/** to the product-catalog service. "
            f"Got {response.status_code}: {response.text}"
        )

    def test_users_route_reaches_user_service(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """/users/** must be forwarded to the user service (port 8082).

        Uses a valid token.  A 200 or 404 from the user service confirms the
        route is wired; a 502/503 indicates the service is not running or the
        gateway routing is broken.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            timeout=10,
        )
        assert response.status_code < 500, (
            f"Gateway failed to route /users/** to the user service. "
            f"Got {response.status_code}: {response.text}"
        )

    def test_prefix_rewrite_is_applied(self, gateway_url: str) -> None:
        """/auth/register via the gateway must map to /api/v1/auth/register.

        The PrefixPath=/api/v1 filter must be applied by the gateway so the
        auth service sees the full /api/v1/auth/register path.  We verify this
        indirectly: a 400 from the auth service (validation failure on the
        empty body) proves the correct endpoint was reached.  If the prefix
        were missing, the auth service would return 404 (no route at /auth/).
        """
        response = httpx.post(
            f"{gateway_url}/auth/register",
            json={},  # empty body → auth service returns 400 (validation error)
            timeout=10,
        )
        assert response.status_code == 400, (
            f"Expected 400 (auth service validated the request) which proves "
            f"PrefixPath rewrite is working. Got {response.status_code}: "
            f"{response.text}"
        )


# ===========================================================================
# Section 5 – Unknown route handling
#
# Paths not matching any configured route predicate should produce a 404
# response from the gateway itself, not a 500 or a proxied error.
# ===========================================================================

class TestUnknownRoutes:
    """Paths not matched by any gateway route must return 404."""

    def test_completely_unknown_path_returns_404(self, gateway_url: str) -> None:
        """GET /no-such-service/endpoint → 404 from the gateway.

        Spring Cloud Gateway returns 404 for paths that do not match any
        route predicate.  This ensures no catch-all route exists that would
        silently swallow unknown requests.
        """
        response = httpx.get(
            f"{gateway_url}/no-such-service/endpoint",
            timeout=10,
        )
        assert response.status_code == 404, (
            f"Expected 404 for unmapped path, got {response.status_code}: "
            f"{response.text}"
        )

    def test_cart_route_not_yet_configured_returns_404(
        self, gateway_url: str
    ) -> None:
        """GET /cart/ → 404 — Cart Service route is not configured in the gateway.

        The Cart Service (port 8084) is listed as 'Not Started' in CLAUDE.md.
        Its route is not in application.yml.  A 404 confirms the gateway does
        not have a stray route for /cart/.

        When the Cart Service is implemented, remove this test and add a
        proper routing + JWT test in its place.
        """
        response = httpx.get(
            f"{gateway_url}/cart/",
            timeout=10,
        )
        assert response.status_code == 404, (
            f"Expected 404 (/cart is not a configured gateway route), "
            f"got {response.status_code}: {response.text}"
        )

    def test_order_route_not_yet_configured_returns_404(
        self, gateway_url: str
    ) -> None:
        """GET /orders/ → 404 — Order Service route is not yet configured."""
        response = httpx.get(
            f"{gateway_url}/orders/",
            timeout=10,
        )
        assert response.status_code == 404, (
            f"Expected 404 (/orders is not a configured gateway route), "
            f"got {response.status_code}: {response.text}"
        )

    def test_root_path_returns_404(self, gateway_url: str) -> None:
        """GET / → 404 — no root-level route is configured."""
        response = httpx.get(
            f"{gateway_url}/",
            timeout=10,
        )
        assert response.status_code == 404, (
            f"Expected 404 for root path, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Section 6 – Token refresh is accessible through the gateway
#
# /auth/refresh uses an HttpOnly cookie rather than a Bearer token.
# The JWT filter must pass /auth/** through unchanged so the cookie-based
# refresh flow works.
# ===========================================================================

class TestRefreshTokenRoute:
    """POST /auth/refresh must be reachable without a Bearer token."""

    def test_refresh_without_cookie_returns_403(self, gateway_url: str) -> None:
        """POST /auth/refresh with no cookie → 403 (from the auth service).

        The auth service returns 403 when the refresh_token cookie is absent
        (see AuthController).  A 403 here proves:
          1. The gateway JWT filter did NOT block the request (that would be 401).
          2. The /auth/refresh endpoint was reached on the auth service.
          3. The auth service's own guard on the missing cookie is working.
        """
        response = httpx.post(
            f"{gateway_url}/auth/refresh",
            timeout=10,
        )
        assert response.status_code == 403, (
            f"Expected 403 (auth service rejects missing cookie) — not 401 "
            f"(that would mean the gateway JWT filter wrongly blocked /auth/). "
            f"Got {response.status_code}: {response.text}"
        )

    def test_refresh_with_valid_cookie_returns_200(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """POST /auth/refresh with a valid refresh_token cookie → 200.

        Full round-trip: the cookie from the login response is sent back and
        the auth service should return a new access token.  The gateway must
        not strip the Cookie header.
        """
        refresh_token = auth_tokens.get("refresh_token")
        if not refresh_token:
            pytest.skip("No refresh_token cookie was captured during login — cannot test refresh flow")

        response = httpx.post(
            f"{gateway_url}/auth/refresh",
            cookies={"refresh_token": refresh_token},
            timeout=10,
        )
        assert response.status_code == 200, (
            f"Expected 200 for valid refresh token, got {response.status_code}: "
            f"{response.text}"
        )
        body = response.json()
        assert "accessToken" in body or "access_token" in body, (
            f"Refresh response must contain a new access token: {body}"
        )
