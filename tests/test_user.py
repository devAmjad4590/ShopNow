# User Service API Tests
#
# Routes under test (all go through the API Gateway at http://localhost:8080):
#
#   Gateway path                         → User-service path (after PrefixPath=/api/v1)
#   GET  /users/me/profile               → GET  /api/v1/users/me/profile
#   PUT  /users/me/profile               → PUT  /api/v1/users/me/profile
#   GET  /users/me/addresses             → GET  /api/v1/users/me/addresses
#   POST /users/me/addresses             → POST /api/v1/users/me/addresses
#   PUT  /users/me/addresses/{id}        → PUT  /api/v1/users/me/addresses/{id}
#   DELETE /users/me/addresses/{id}      → DELETE /api/v1/users/me/addresses/{id}
#   GET  /users/{id}                     → GET  /api/v1/users/{id}  (admin only)
#
# Auth model:
#   All /users/** routes pass through JWTAuthenticationFilter which requires a
#   valid "Authorization: Bearer <token>" header. The gateway then injects
#   X-User-Id and X-User-Role headers that the user-service controllers read.
#
# Run:
#   pytest tests/test_user.py -v
# Prerequisites:
#   All services running: docker compose up -d && mvn spring-boot:run (per service)

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bearer(token: str) -> dict:
    """Return an Authorization header dict for the given JWT."""
    return {"Authorization": f"Bearer {token}"}


VALID_ADDRESS = {
    "label": "Home",
    "line1": "123 Main Street",
    "line2": "Apt 4B",
    "city": "Springfield",
    "state": "IL",
    "country": "US",
    "postalCode": "62701",
    "isDefault": True,
}


# ===========================================================================
# Profile — GET /users/me/profile
# ===========================================================================

class TestGetProfile:

    def test_get_profile_happy_path(self, gateway_url: str, auth_tokens: dict) -> None:
        """
        Authenticated user fetches their own profile.
        Expected: 200 with a ProfileResponse body containing authUserId.
        A freshly registered user has no profile row yet; the service should
        either return a default/empty profile or 404. We assert 200 or 404 and
        treat both as valid depending on whether the service auto-creates a row.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers=bearer(auth_tokens["access_token"]),
        )
        # Service may return 200 (profile exists/auto-created) or 404 (not yet set up)
        assert response.status_code in (200, 404), (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        if response.status_code == 200:
            body = response.json()
            assert "authUserId" in body, f"authUserId missing from profile: {body}"

    def test_get_profile_returns_401_without_token(self, gateway_url: str) -> None:
        """
        Request without Authorization header is rejected by the gateway.
        Expected: 401 Unauthorized.
        """
        response = httpx.get(f"{gateway_url}/users/me/profile")
        assert response.status_code == 401, (
            f"Expected 401 without token, got {response.status_code}: {response.text}"
        )

    def test_get_profile_returns_401_with_invalid_token(self, gateway_url: str) -> None:
        """
        Request with a malformed/invalid JWT is rejected by the gateway's
        JWTAuthenticationFilter before reaching the user-service.
        Expected: 401 Unauthorized.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
        )
        assert response.status_code == 401, (
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"
        )

    def test_get_profile_returns_401_with_empty_bearer(self, gateway_url: str) -> None:
        """
        'Authorization: Bearer ' with no token value — should be caught by
        the gateway filter which checks for 'Bearer ' prefix and then passes
        the empty string to jwtService.isTokenValid(), which should fail.
        Expected: 401 Unauthorized.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/profile",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401, (
            f"Expected 401 for empty bearer, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Profile — PUT /users/me/profile
# ===========================================================================

class TestUpdateProfile:

    def test_update_profile_happy_path(self, gateway_url: str, auth_tokens: dict) -> None:
        """
        Authenticated user updates their profile with valid fields.
        Expected: 200 with updated ProfileResponse.
        """
        payload = {
            "phone": "+12025550199",
            "dateOfBirth": "1990-06-15",
            "avatarUrl": "https://cdn.shopnow.test/avatars/testuser.png",
            "bio": "Just a test account — feel free to ignore.",
        }
        response = httpx.put(
            f"{gateway_url}/users/me/profile",
            json=payload,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 200, (
            f"Expected 200 on profile update, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("phone") == payload["phone"], (
            f"phone not updated: {body}"
        )
        assert body.get("bio") == payload["bio"], (
            f"bio not updated: {body}"
        )

    def test_update_profile_invalid_phone_returns_400(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        Phone field fails the @Pattern(regexp="^\\+?[0-9]{7,15}$") constraint.
        Expected: 400 with VALIDATION_ERROR in the body.
        """
        response = httpx.put(
            f"{gateway_url}/users/me/profile",
            json={"phone": "not-a-phone"},
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 400, (
            f"Expected 400 for invalid phone, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("error") == "VALIDATION_ERROR", (
            f"Expected VALIDATION_ERROR, got: {body}"
        )

    def test_update_profile_all_optional_fields_can_be_null(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        ProfileUpdateRequest has no @NotBlank fields — all fields are optional.
        Sending an empty body should still succeed.
        Expected: 200.
        """
        response = httpx.put(
            f"{gateway_url}/users/me/profile",
            json={},
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 200, (
            f"Expected 200 for empty update body, got {response.status_code}: {response.text}"
        )

    def test_update_profile_returns_401_without_token(self, gateway_url: str) -> None:
        """
        No Authorization header → gateway rejects before reaching the service.
        Expected: 401 Unauthorized.
        """
        response = httpx.put(
            f"{gateway_url}/users/me/profile",
            json={"bio": "sneaky update"},
        )
        assert response.status_code == 401, (
            f"Expected 401 without token, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Addresses — GET /users/me/addresses
# ===========================================================================

class TestListAddresses:

    def test_list_addresses_happy_path(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        Authenticated user lists their addresses (may be empty initially).
        Expected: 200 with a JSON array.
        """
        response = httpx.get(
            f"{gateway_url}/users/me/addresses",
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 200, (
            f"Expected 200 for list addresses, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert isinstance(body, list), (
            f"Expected JSON array from list addresses, got {type(body).__name__}: {body!r}"
        )

    def test_list_addresses_returns_401_without_token(self, gateway_url: str) -> None:
        """
        No token → gateway rejects.
        Expected: 401 Unauthorized.
        """
        response = httpx.get(f"{gateway_url}/users/me/addresses")
        assert response.status_code == 401, (
            f"Expected 401 without token, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Addresses — POST /users/me/addresses
# ===========================================================================

class TestCreateAddress:

    def test_create_address_happy_path(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        Authenticated user creates a new address with all required fields.
        Expected: 201 with AddressResponse containing the generated id.
        """
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json=VALID_ADDRESS,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 201, (
            f"Expected 201 for create address, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "id" in body, f"Response missing 'id' field: {body}"
        assert body["line1"] == VALID_ADDRESS["line1"], (
            f"line1 not persisted correctly: {body}"
        )
        assert body["city"] == VALID_ADDRESS["city"], (
            f"city not persisted correctly: {body}"
        )

    def test_create_address_missing_line1_returns_400(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        line1 is @NotBlank — omitting it triggers a validation error.
        Expected: 400 with VALIDATION_ERROR.
        """
        payload = {k: v for k, v in VALID_ADDRESS.items() if k != "line1"}
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json=payload,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 400, (
            f"Expected 400 for missing line1, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("error") == "VALIDATION_ERROR", f"Unexpected error body: {body}"

    def test_create_address_missing_city_returns_400(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        city is @NotBlank — omitting it triggers a validation error.
        Expected: 400 with VALIDATION_ERROR.
        """
        payload = {k: v for k, v in VALID_ADDRESS.items() if k != "city"}
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json=payload,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 400, (
            f"Expected 400 for missing city, got {response.status_code}: {response.text}"
        )

    def test_create_address_missing_country_returns_400(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        country is @NotBlank — omitting it triggers a validation error.
        Expected: 400 with VALIDATION_ERROR.
        """
        payload = {k: v for k, v in VALID_ADDRESS.items() if k != "country"}
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json=payload,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 400, (
            f"Expected 400 for missing country, got {response.status_code}: {response.text}"
        )

    def test_create_address_missing_postal_code_returns_400(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        postalCode is @NotBlank — omitting it triggers a validation error.
        Expected: 400 with VALIDATION_ERROR.
        """
        payload = {k: v for k, v in VALID_ADDRESS.items() if k != "postalCode"}
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json=payload,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 400, (
            f"Expected 400 for missing postalCode, got {response.status_code}: {response.text}"
        )

    def test_create_address_optional_fields_can_be_omitted(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        label, line2, and state are optional (no @NotBlank).
        Sending only the required four fields should succeed.
        Expected: 201.
        """
        minimal = {
            "line1": "456 Oak Avenue",
            "city": "Shelbyville",
            "country": "US",
            "postalCode": "62565",
        }
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json=minimal,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 201, (
            f"Expected 201 for minimal address, got {response.status_code}: {response.text}"
        )

    def test_create_address_returns_401_without_token(self, gateway_url: str) -> None:
        """
        No token → gateway rejects.
        Expected: 401 Unauthorized.
        """
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json=VALID_ADDRESS,
        )
        assert response.status_code == 401, (
            f"Expected 401 without token, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Addresses — PUT /users/me/addresses/{id}
# ===========================================================================

class TestUpdateAddress:
    """
    These tests depend on having created an address first.
    The create_address fixture creates one and returns its id.
    """

    @pytest.fixture(scope="class")
    def created_address_id(self, gateway_url: str, auth_tokens: dict) -> int:
        """Create a fresh address and return its id for update/delete tests."""
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json={
                "label": "Work",
                "line1": "1 Corporate Plaza",
                "city": "Chicago",
                "state": "IL",
                "country": "US",
                "postalCode": "60601",
                "isDefault": False,
            },
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 201, (
            f"Setup fixture failed: {response.status_code} {response.text}"
        )
        return response.json()["id"]

    def test_update_address_happy_path(
        self, gateway_url: str, auth_tokens: dict, created_address_id: int
    ) -> None:
        """
        Update an existing address with a new city and line1.
        Expected: 200 with updated AddressResponse.
        """
        updated = {
            "label": "Work (updated)",
            "line1": "2 Corporate Plaza",
            "city": "Evanston",
            "state": "IL",
            "country": "US",
            "postalCode": "60201",
            "isDefault": False,
        }
        response = httpx.put(
            f"{gateway_url}/users/me/addresses/{created_address_id}",
            json=updated,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 200, (
            f"Expected 200 on address update, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["city"] == "Evanston", f"city not updated: {body}"
        assert body["line1"] == "2 Corporate Plaza", f"line1 not updated: {body}"

    def test_update_address_not_found_returns_404(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        Attempt to update an address id that does not exist for this user.
        AddressService throws ResponseStatusException(NOT_FOUND).
        Expected: 404.
        """
        response = httpx.put(
            f"{gateway_url}/users/me/addresses/999999",
            json=VALID_ADDRESS,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 404, (
            f"Expected 404 for non-existent address, got {response.status_code}: {response.text}"
        )

    def test_update_address_missing_required_field_returns_400(
        self, gateway_url: str, auth_tokens: dict, created_address_id: int
    ) -> None:
        """
        Omit line1 (@NotBlank) from the update payload.
        Expected: 400 with VALIDATION_ERROR.
        """
        bad_payload = {
            "city": "Chicago",
            "country": "US",
            "postalCode": "60601",
        }
        response = httpx.put(
            f"{gateway_url}/users/me/addresses/{created_address_id}",
            json=bad_payload,
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 400, (
            f"Expected 400 for missing line1 in update, got {response.status_code}: {response.text}"
        )

    def test_update_address_returns_401_without_token(
        self, gateway_url: str, created_address_id: int
    ) -> None:
        """
        No token → gateway rejects.
        Expected: 401.
        """
        response = httpx.put(
            f"{gateway_url}/users/me/addresses/{created_address_id}",
            json=VALID_ADDRESS,
        )
        assert response.status_code == 401, (
            f"Expected 401 without token, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Addresses — DELETE /users/me/addresses/{id}
# ===========================================================================

class TestDeleteAddress:

    @pytest.fixture()
    def disposable_address_id(self, gateway_url: str, auth_tokens: dict) -> int:
        """
        Create a fresh address before each delete test so each test gets its
        own address to delete. Function-scoped so it runs per test.
        """
        response = httpx.post(
            f"{gateway_url}/users/me/addresses",
            json={
                "line1": "789 Disposable Lane",
                "city": "Deleteville",
                "country": "US",
                "postalCode": "00001",
            },
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 201, (
            f"Delete-test setup fixture failed: {response.status_code} {response.text}"
        )
        return response.json()["id"]

    def test_delete_address_happy_path(
        self, gateway_url: str, auth_tokens: dict, disposable_address_id: int
    ) -> None:
        """
        Delete an address that belongs to the current user.
        Expected: 204 No Content with no response body.
        """
        response = httpx.delete(
            f"{gateway_url}/users/me/addresses/{disposable_address_id}",
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 204, (
            f"Expected 204 on delete, got {response.status_code}: {response.text}"
        )

    def test_delete_address_is_idempotent_on_second_call(
        self, gateway_url: str, auth_tokens: dict, disposable_address_id: int
    ) -> None:
        """
        Delete the same address twice — the second call should return 404
        because the record no longer exists (AddressService.findByIdAndAuthUserId
        throws NOT_FOUND).
        Expected: 204 on first call, 404 on second call.
        """
        first = httpx.delete(
            f"{gateway_url}/users/me/addresses/{disposable_address_id}",
            headers=bearer(auth_tokens["access_token"]),
        )
        assert first.status_code == 204, (
            f"First delete: expected 204, got {first.status_code}: {first.text}"
        )

        second = httpx.delete(
            f"{gateway_url}/users/me/addresses/{disposable_address_id}",
            headers=bearer(auth_tokens["access_token"]),
        )
        assert second.status_code == 404, (
            f"Second delete: expected 404, got {second.status_code}: {second.text}"
        )

    def test_delete_address_not_found_returns_404(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        Delete a non-existent address id.
        Expected: 404.
        """
        response = httpx.delete(
            f"{gateway_url}/users/me/addresses/999999",
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 404, (
            f"Expected 404 for missing address, got {response.status_code}: {response.text}"
        )

    def test_delete_address_returns_401_without_token(
        self, gateway_url: str, disposable_address_id: int
    ) -> None:
        """
        No token → gateway rejects.
        Expected: 401.
        """
        response = httpx.delete(
            f"{gateway_url}/users/me/addresses/{disposable_address_id}",
        )
        assert response.status_code == 401, (
            f"Expected 401 without token, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Admin — GET /users/{id}
# ===========================================================================

class TestAdminGetUser:
    """
    GET /users/{id} is handled by AdminUserController.
    The controller manually inspects the X-User-Role header (injected by the
    gateway from the JWT claims). Only users whose JWT was issued with
    role=ADMIN may call this endpoint — all others receive 403.

    Note: The test user registered by the registered_user fixture is created
    with the default role (USER), not ADMIN. There is no admin registration
    endpoint, so we can only test the 403 path here without a pre-seeded
    ADMIN account in the database.
    """

    def test_admin_get_user_as_regular_user_returns_403(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        A regular USER-role token is rejected by AdminUserController's manual
        role check (role != "ADMIN" → ResponseStatusException FORBIDDEN).
        Expected: 403 Forbidden.
        """
        response = httpx.get(
            f"{gateway_url}/users/1",
            headers=bearer(auth_tokens["access_token"]),
        )
        assert response.status_code == 403, (
            f"Expected 403 for non-admin accessing admin route, "
            f"got {response.status_code}: {response.text}"
        )

    def test_admin_get_user_returns_401_without_token(self, gateway_url: str) -> None:
        """
        No token → gateway rejects before the controller is reached.
        Expected: 401 Unauthorized.
        """
        response = httpx.get(f"{gateway_url}/users/1")
        assert response.status_code == 401, (
            f"Expected 401 without token, got {response.status_code}: {response.text}"
        )

    def test_admin_get_user_returns_401_with_invalid_token(
        self, gateway_url: str
    ) -> None:
        """
        Tampered/expired JWT → gateway filter rejects.
        Expected: 401 Unauthorized.
        """
        response = httpx.get(
            f"{gateway_url}/users/1",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.tampered.sig"},
        )
        assert response.status_code == 401, (
            f"Expected 401 for tampered token, got {response.status_code}: {response.text}"
        )
