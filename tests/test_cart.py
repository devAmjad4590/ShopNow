"""
Cart Service — integration tests
=================================
All gateway-routed requests target http://localhost:8080 which routes:
  /cart/**  →  PrefixPath=/api/v1  →  cart-service at localhost:8084

Gateway auth behaviour (JWTAuthenticationFilter):
  The filter only enforces auth on /users/** and non-GET /products|/categories.
  /cart/** is NOT in the gateway's requiresAuth list, so the gateway forwards
  cart requests unconditionally — no Bearer token is checked at the gateway.

Cart service auth behaviour:
  CartController reads @RequestHeader("X-User-Id") on every endpoint. The gateway
  injects this header only when a valid Bearer token is present (from the JWT).
  Without a valid token the header is absent, causing Spring to respond 400
  (MissingRequestHeaderException). There is no GlobalExceptionHandler mapping for
  that exception, so it propagates as a 400 Bad Request from the default Spring
  error handling.

  Consequence: missing/invalid JWT → 400 (not 401) on cart routes.
  Tests for "no auth" scenarios use the comment "gateway passes through; service
  rejects with 400 (missing X-User-Id header)" to explain this behaviour.

Internal endpoint behaviour:
  GET /api/v1/internal/cart/{userId} is served directly at port 8084. The
  api-gateway has no route for /internal/**, so requests via the gateway at
  /internal/cart/{userId} return 404 from the gateway itself.
  Tests for the internal endpoint hit port 8084 directly.

Prerequisites:
  - Full stack must be running: gateway, auth-service, cart-service, product-catalog,
    postgres, redis.
  - The shared conftest.py fixtures (gateway_url, auth_tokens, registered_user) must
    be available.

Run:
  pytest tests/test_cart.py -v

Environment variables:
  GATEWAY_URL      — override gateway base URL (default: http://localhost:8080)
  CART_DIRECT_URL  — override direct cart-service URL (default: http://localhost:8084/api/v1)
  KNOWN_PRODUCT_ID — integer product ID that exists in the product-catalog for
                     add-item happy-path tests. If not set, tests that require a
                     real product are skipped. Set this to any product you have
                     seeded (e.g., via test_product.py admin tests).
"""

import os
import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CART_DIRECT_URL = os.environ.get("CART_DIRECT_URL", "http://localhost:8084/api/v1")

# Product ID that is known to exist in the catalog.
# Required for tests that call POST /cart/items (which validates via product-catalog).
_KNOWN_PRODUCT_ID_ENV = os.environ.get("KNOWN_PRODUCT_ID")
KNOWN_PRODUCT_ID: int | None = int(_KNOWN_PRODUCT_ID_ENV) if _KNOWN_PRODUCT_ID_ENV else None

# A product ID that is guaranteed not to exist (very large number).
NONEXISTENT_PRODUCT_ID = 999_999_999


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_headers(access_token: str) -> dict:
    """Build an Authorization header dict from a bearer token."""
    return {"Authorization": f"Bearer {access_token}"}


def _require_known_product():
    """Skip a test if KNOWN_PRODUCT_ID env var is not set."""
    if KNOWN_PRODUCT_ID is None:
        pytest.skip(
            "KNOWN_PRODUCT_ID env var is not set. "
            "Set it to a valid product ID from the catalog to run this test."
        )


# ---------------------------------------------------------------------------
# Module-scoped fixture: a fresh cart that has one item added to it.
#
# We use function scope for most cart tests because cart state is per-user and
# mutating tests would interfere with each other if the same user were shared.
# The conftest.py auth_tokens fixture is session-scoped, so all cart tests
# share the same JWT user. Each test class that mutates the cart clears it
# in a setup step to start from a known state.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cart_user_token(auth_tokens: dict) -> str:
    """Return the access token for the session user. Alias for readability."""
    return auth_tokens["access_token"]


# ===========================================================================
# GET /cart — retrieve current cart
# ===========================================================================

class TestGetCart:
    """GET /cart via API Gateway — requires valid JWT."""

    def test_empty_cart_returns_200_with_empty_items(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        A user with no items should receive HTTP 200 and an empty items array.
        We clear the cart first to guarantee a clean state.
        Expected response shape:
          { userId, items: [], totalAmount: 0, updatedAt }
        """
        # Ensure a clean slate.
        httpx.delete(
            f"{gateway_url}/cart",
            headers=auth_headers(cart_user_token),
        )

        response = httpx.get(
            f"{gateway_url}/cart",
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "userId" in body, f"'userId' missing from CartResponse: {body}"
        assert "items" in body, f"'items' missing from CartResponse: {body}"
        assert "totalAmount" in body, f"'totalAmount' missing from CartResponse: {body}"
        assert "updatedAt" in body, f"'updatedAt' missing from CartResponse: {body}"
        assert body["items"] == [], (
            f"Expected empty items list after clear, got: {body['items']}"
        )
        assert float(body["totalAmount"]) == 0.0, (
            f"Expected totalAmount == 0 for empty cart, got: {body['totalAmount']}"
        )

    def test_response_shape_has_all_required_fields(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """CartResponse must always include userId, items, totalAmount, updatedAt."""
        response = httpx.get(
            f"{gateway_url}/cart",
            headers=auth_headers(cart_user_token),
        )
        assert response.status_code == 200
        body = response.json()
        for field in ("userId", "items", "totalAmount", "updatedAt"):
            assert field in body, f"Required field '{field}' missing from CartResponse: {body}"

    def test_no_token_returns_400(self, gateway_url: str) -> None:
        """
        No Bearer token → gateway passes through (no auth enforcement on /cart/**),
        but cart-service raises MissingRequestHeaderException for X-User-Id → 400.
        """
        response = httpx.get(f"{gateway_url}/cart")
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id header) but got {response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_400(self, gateway_url: str) -> None:
        """
        An invalid JWT is not validated by the gateway for /cart/** routes.
        The gateway injects no X-User-Id header (only valid tokens trigger injection).
        The service then rejects with 400 due to missing X-User-Id.
        """
        response = httpx.get(
            f"{gateway_url}/cart",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
        )
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id after invalid JWT) but got "
            f"{response.status_code}: {response.text}"
        )


# ===========================================================================
# POST /cart/items — add item to cart
# ===========================================================================

class TestAddItem:
    """POST /cart/items via API Gateway — requires valid JWT and a real product ID."""

    def test_happy_path_returns_200_with_cart_containing_item(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Adding a valid product (existing in catalog) returns 200 and the updated
        cart with the item's productId, productName, price, quantity, and imageUrl.
        """
        _require_known_product()

        # Start from a clean cart.
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 2},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert len(body["items"]) == 1, (
            f"Expected 1 item in cart after add, got {len(body['items'])}: {body['items']}"
        )
        item = body["items"][0]
        assert item["productId"] == KNOWN_PRODUCT_ID
        assert item["quantity"] == 2
        assert "productName" in item, f"'productName' missing from CartItem: {item}"
        assert "price" in item, f"'price' missing from CartItem: {item}"
        assert float(body["totalAmount"]) > 0, (
            f"totalAmount should be positive after adding an item: {body['totalAmount']}"
        )

        # Cleanup.
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

    def test_adding_same_product_twice_accumulates_quantity(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Adding the same productId twice must NOT create a duplicate item.
        The service merges by productId, so quantity should be the sum of both calls.
        (First add: qty 1, second add: qty 3 → final qty 4.)
        """
        _require_known_product()

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 1},
            headers=auth_headers(cart_user_token),
        )
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 3},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert len(body["items"]) == 1, (
            f"Expected 1 item (merged duplicate), got {len(body['items'])}: {body['items']}"
        )
        assert body["items"][0]["quantity"] == 4, (
            f"Expected merged quantity 4 (1+3), got {body['items'][0]['quantity']}"
        )

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

    def test_total_amount_is_calculated_correctly(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        totalAmount must equal price * quantity summed across all items.
        We add one product with a known quantity and verify the math.
        """
        _require_known_product()

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 3},
            headers=auth_headers(cart_user_token),
        )
        assert response.status_code == 200
        body = response.json()
        item = body["items"][0]
        expected_total = float(item["price"]) * item["quantity"]
        actual_total = float(body["totalAmount"])
        assert abs(actual_total - expected_total) < 0.01, (
            f"totalAmount mismatch: expected {expected_total}, got {actual_total}"
        )

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

    def test_nonexistent_product_id_returns_404(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Adding a productId that does not exist in the catalog triggers
        ProductCatalogClient to raise ProductNotFoundException → 404.
        ErrorResponse shape: { status: 404, error: "Not Found", message, timestamp }
        """
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": NONEXISTENT_PRODUCT_ID, "quantity": 1},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 404, (
            f"Expected 404 for non-existent product but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 404
        assert "Not Found" in body.get("error", ""), (
            f"Expected 'Not Found' in error field, got: {body}"
        )
        assert str(NONEXISTENT_PRODUCT_ID) in body.get("message", ""), (
            f"Expected product ID in error message, got: {body.get('message')}"
        )

    def test_missing_product_id_returns_400(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        productId is @NotNull — omitting it from the request body triggers
        MethodArgumentNotValidException → 400.
        """
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"quantity": 2},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 when productId is missing, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400
        assert body.get("error") == "Bad Request"

    def test_zero_quantity_returns_400(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        quantity has @Min(1) on AddItemRequest — sending 0 fails validation → 400.
        (Note: UpdateItemRequest allows 0 as a 'remove' signal, but AddItemRequest does not.)
        """
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID or 1, "quantity": 0},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 for quantity=0 on add, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400

    def test_negative_quantity_returns_400(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        quantity has @Min(1) — sending a negative value fails validation → 400.
        """
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID or 1, "quantity": -5},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 for negative quantity, got {response.status_code}: {response.text}"
        )

    def test_empty_body_returns_400(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """An empty JSON object fails both @NotNull productId and @Min(1) quantity → 400."""
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 for empty body, got {response.status_code}: {response.text}"
        )

    def test_no_token_returns_400(self, gateway_url: str) -> None:
        """
        No Bearer token → gateway does not inject X-User-Id → service returns 400.
        (The gateway does not enforce auth on /cart/** routes.)
        """
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": 1, "quantity": 1},
        )
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id) but got {response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_400(self, gateway_url: str) -> None:
        """
        An invalid JWT is not rejected at the gateway for /cart/**. The gateway
        skips X-User-Id injection (only valid tokens trigger it), so the service
        receives no X-User-Id header → 400.
        """
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": 1, "quantity": 1},
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"},
        )
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id after invalid JWT) but got "
            f"{response.status_code}: {response.text}"
        )


# ===========================================================================
# PUT /cart/items/{productId} — update item quantity
# ===========================================================================

class TestUpdateItem:
    """PUT /cart/items/{productId} via API Gateway — requires valid JWT."""

    def _seed_item(self, gateway_url: str, token: str) -> None:
        """Helper: clear cart and add one known product so update tests have state."""
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(token))
        httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 2},
            headers=auth_headers(token),
        )

    def test_happy_path_updates_quantity_returns_200(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Updating an existing item's quantity returns 200 with the updated cart.
        The item's quantity is set to the new value (not incremented).
        """
        _require_known_product()
        self._seed_item(gateway_url, cart_user_token)

        response = httpx.put(
            f"{gateway_url}/cart/items/{KNOWN_PRODUCT_ID}",
            json={"quantity": 5},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["quantity"] == 5, (
            f"Expected quantity 5 after update, got {body['items'][0]['quantity']}"
        )

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

    def test_update_quantity_to_zero_removes_item(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        UpdateItemRequest allows quantity=0 (@Min(0)). The service interprets
        quantity=0 as a removal: the item is deleted from the cart and the
        returned items list becomes empty.
        """
        _require_known_product()
        self._seed_item(gateway_url, cart_user_token)

        response = httpx.put(
            f"{gateway_url}/cart/items/{KNOWN_PRODUCT_ID}",
            json={"quantity": 0},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["items"] == [], (
            f"Expected empty cart after setting quantity to 0, got {body['items']}"
        )
        assert float(body["totalAmount"]) == 0.0

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

    def test_update_nonexistent_item_returns_404(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Updating a productId that is not in the cart raises ProductNotFoundException
        → 404. The service throws this rather than silently succeeding.
        """
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        response = httpx.put(
            f"{gateway_url}/cart/items/{NONEXISTENT_PRODUCT_ID}",
            json={"quantity": 3},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 404, (
            f"Expected 404 for product not in cart but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 404
        assert "Not Found" in body.get("error", ""), (
            f"Expected 'Not Found' in error field, got: {body}"
        )

    def test_negative_quantity_returns_400(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        quantity has @Min(0) on UpdateItemRequest — negative values fail
        validation → 400.
        """
        response = httpx.put(
            f"{gateway_url}/cart/items/1",
            json={"quantity": -1},
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 for negative quantity on update, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400
        assert body.get("error") == "Bad Request"

    def test_empty_body_returns_400(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Empty body causes the default int value (0) to be used for quantity, which
        passes @Min(0). However, productId in the path must still be a valid Long.
        This test sends an empty JSON object to verify a parseable response.
        NOTE: an empty body with a valid path variable results in quantity=0 being
        used (Java default), which is allowed by @Min(0) and removes the item if it
        exists. With a non-existent item it returns 404. The test verifies the
        service does not 500 on an empty body.
        """
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        response = httpx.put(
            f"{gateway_url}/cart/items/{NONEXISTENT_PRODUCT_ID}",
            json={},
            headers=auth_headers(cart_user_token),
        )
        # Empty cart + non-existent product → 404 (item not found) or 400 (validation)
        assert response.status_code in (400, 404), (
            f"Expected 400 or 404 for empty body update, got {response.status_code}: {response.text}"
        )

    def test_no_token_returns_400(self, gateway_url: str) -> None:
        """No JWT → no X-User-Id injected → 400 from the service."""
        response = httpx.put(
            f"{gateway_url}/cart/items/1",
            json={"quantity": 2},
        )
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id) but got {response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_400(self, gateway_url: str) -> None:
        """Invalid JWT → no X-User-Id injected → 400 from the service."""
        response = httpx.put(
            f"{gateway_url}/cart/items/1",
            json={"quantity": 2},
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"},
        )
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id) but got {response.status_code}: {response.text}"
        )


# ===========================================================================
# DELETE /cart/items/{productId} — remove a single item
# ===========================================================================

class TestRemoveItem:
    """DELETE /cart/items/{productId} via API Gateway — requires valid JWT."""

    def _seed_item(self, gateway_url: str, token: str) -> None:
        """Helper: clear cart and add one known product."""
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(token))
        httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 2},
            headers=auth_headers(token),
        )

    def test_happy_path_removes_item_returns_200(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Removing an item that exists returns 200 and an updated cart without
        that item. The totalAmount adjusts accordingly.
        """
        _require_known_product()
        self._seed_item(gateway_url, cart_user_token)

        response = httpx.delete(
            f"{gateway_url}/cart/items/{KNOWN_PRODUCT_ID}",
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        remaining_ids = [i["productId"] for i in body["items"]]
        assert KNOWN_PRODUCT_ID not in remaining_ids, (
            f"Product {KNOWN_PRODUCT_ID} still in cart after removal: {body['items']}"
        )
        assert float(body["totalAmount"]) == 0.0

    def test_remove_nonexistent_item_returns_200_silently(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Removing a productId that is not in the cart is a no-op in the service:
        removeIf on an empty list simply does nothing and the call returns 200
        with the unchanged (empty) cart. This is intentional — no 404 is raised.
        """
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        response = httpx.delete(
            f"{gateway_url}/cart/items/{NONEXISTENT_PRODUCT_ID}",
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 (silent no-op) for removing non-existent item, "
            f"got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["items"] == [], (
            f"Expected empty items list after no-op remove: {body['items']}"
        )

    def test_remove_one_of_multiple_items_leaves_others_intact(
        self, gateway_url: str, cart_user_token: str, auth_tokens: dict
    ) -> None:
        """
        With two products in the cart, removing one must leave the other
        untouched. We use two distinct product IDs if a second one is available.
        This test is skipped if only one known product ID is available.
        """
        _require_known_product()

        second_product_id = os.environ.get("KNOWN_PRODUCT_ID_2")
        if second_product_id is None:
            pytest.skip(
                "KNOWN_PRODUCT_ID_2 env var not set — cannot test multi-item removal. "
                "Set it to a second valid product ID."
            )
        second_product_id = int(second_product_id)

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))
        httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 1},
            headers=auth_headers(cart_user_token),
        )
        httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": second_product_id, "quantity": 1},
            headers=auth_headers(cart_user_token),
        )

        response = httpx.delete(
            f"{gateway_url}/cart/items/{KNOWN_PRODUCT_ID}",
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 200
        body = response.json()
        remaining_ids = [i["productId"] for i in body["items"]]
        assert KNOWN_PRODUCT_ID not in remaining_ids, (
            f"Removed product {KNOWN_PRODUCT_ID} still in cart"
        )
        assert second_product_id in remaining_ids, (
            f"Product {second_product_id} should still be in cart"
        )

        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

    def test_no_token_returns_400(self, gateway_url: str) -> None:
        """No JWT → no X-User-Id injected → 400 from the service."""
        response = httpx.delete(f"{gateway_url}/cart/items/1")
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id) but got {response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_400(self, gateway_url: str) -> None:
        """Invalid JWT → no X-User-Id injected → 400 from the service."""
        response = httpx.delete(
            f"{gateway_url}/cart/items/1",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"},
        )
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id) but got {response.status_code}: {response.text}"
        )


# ===========================================================================
# DELETE /cart — clear the entire cart
# ===========================================================================

class TestClearCart:
    """DELETE /cart via API Gateway — requires valid JWT."""

    def test_clear_non_empty_cart_returns_204(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Clearing a cart that has items returns 204 No Content.
        Subsequent GET /cart must return an empty items list.
        """
        _require_known_product()

        # Seed an item so the cart is non-empty.
        httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 1},
            headers=auth_headers(cart_user_token),
        )

        response = httpx.delete(
            f"{gateway_url}/cart",
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 204, (
            f"Expected 204 No Content but got {response.status_code}: {response.text}"
        )
        assert response.content == b"", (
            "204 response must have no body"
        )

        # Verify the cart is truly empty afterwards.
        get_response = httpx.get(
            f"{gateway_url}/cart",
            headers=auth_headers(cart_user_token),
        )
        assert get_response.status_code == 200
        assert get_response.json()["items"] == []

    def test_clear_already_empty_cart_returns_204(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        Clearing an already-empty cart is a no-op and must still return 204.
        Redis DELETE on a non-existent key is idempotent.
        """
        # Ensure cart is empty first.
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        response = httpx.delete(
            f"{gateway_url}/cart",
            headers=auth_headers(cart_user_token),
        )

        assert response.status_code == 204, (
            f"Expected 204 for already-empty cart but got {response.status_code}: {response.text}"
        )

    def test_cleared_cart_is_inaccessible_with_old_data(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        After clearing, GET /cart must return a fresh empty CartResponse rather
        than any cached/stale state. The Redis key is deleted, so getCart falls
        back to emptyCart() which returns a zero-item cart.
        """
        _require_known_product()

        httpx.post(
            f"{gateway_url}/cart/items",
            json={"productId": KNOWN_PRODUCT_ID, "quantity": 3},
            headers=auth_headers(cart_user_token),
        )
        httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        get_response = httpx.get(
            f"{gateway_url}/cart",
            headers=auth_headers(cart_user_token),
        )
        body = get_response.json()
        assert body["items"] == [], (
            f"Expected empty items after clear, got: {body['items']}"
        )
        assert float(body["totalAmount"]) == 0.0

    def test_no_token_returns_400(self, gateway_url: str) -> None:
        """No JWT → no X-User-Id injected → 400 from the service."""
        response = httpx.delete(f"{gateway_url}/cart")
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id) but got {response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_400(self, gateway_url: str) -> None:
        """Invalid JWT → no X-User-Id injected → 400 from the service."""
        response = httpx.delete(
            f"{gateway_url}/cart",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"},
        )
        assert response.status_code == 400, (
            f"Expected 400 (missing X-User-Id) but got {response.status_code}: {response.text}"
        )


# ===========================================================================
# Internal endpoint: GET /api/v1/internal/cart/{userId}
# Hits the cart-service directly at port 8084 — NOT via the gateway.
# ===========================================================================

class TestInternalCartEndpoint:
    """
    GET /api/v1/internal/cart/{userId} — direct service call, no JWT required.

    This endpoint exists for inter-service communication (e.g., order-service
    fetching a user's cart before creating an order). It is intentionally not
    exposed via the API gateway (no /internal/** route in application.yml).

    Two sub-classes:
      TestInternalCartGatewayBlocked  — verifies gateway returns 404 for the path
      TestInternalCartDirect          — verifies correct behaviour at direct port
    """

    class TestGatewayDoesNotExposeInternalRoute:
        """The gateway must not route /internal/cart/* to the cart-service."""

        def test_internal_cart_via_gateway_returns_404(
            self, gateway_url: str, auth_tokens: dict
        ) -> None:
            """
            /internal/cart/{userId} has no matching gateway route.
            The gateway returns 404 — the cart-service is never reached.
            """
            response = httpx.get(
                f"{gateway_url}/internal/cart/some-user-id",
                headers=auth_headers(auth_tokens["access_token"]),
            )
            assert response.status_code == 404, (
                f"Expected 404 (no gateway route for /internal/cart/**) but got "
                f"{response.status_code}: {response.text}"
            )

        def test_internal_cart_via_gateway_without_token_also_returns_404(
            self, gateway_url: str
        ) -> None:
            """
            Even without a token the gateway returns 404 for this path.
            If this starts returning 401, a route was added without auth protection.
            """
            response = httpx.get(f"{gateway_url}/internal/cart/some-user-id")
            assert response.status_code == 404, (
                f"Expected 404 (no gateway route) but got {response.status_code}: {response.text}"
            )

    class TestDirectServiceCall:
        """Directly call the cart-service on port 8084 (bypassing the gateway)."""

        def test_returns_200_for_user_with_no_cart(self) -> None:
            """
            A userId with no cart in Redis → CartService.emptyCart() is returned.
            Expected: 200 with empty items list.
            The internal endpoint requires no authentication header.
            """
            unknown_user = f"test-internal-{uuid.uuid4().hex[:8]}"
            response = httpx.get(f"{CART_DIRECT_URL}/internal/cart/{unknown_user}")

            assert response.status_code == 200, (
                f"Expected 200 for unknown user (empty cart) but got "
                f"{response.status_code}: {response.text}"
            )
            body = response.json()
            assert body["userId"] == unknown_user
            assert body["items"] == []
            assert float(body["totalAmount"]) == 0.0

        def test_returns_cart_for_user_who_has_items(
            self, gateway_url: str, cart_user_token: str, auth_tokens: dict
        ) -> None:
            """
            After adding an item via the gateway, the internal endpoint at
            port 8084 returns the same cart state for that userId.
            This validates that both paths read from the same Redis key.
            """
            _require_known_product()

            # Extract the userId from a GET /cart call (the response includes it).
            setup_response = httpx.get(
                f"{gateway_url}/cart",
                headers=auth_headers(cart_user_token),
            )
            assert setup_response.status_code == 200
            user_id = setup_response.json()["userId"]

            # Seed the cart via gateway.
            httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))
            add_response = httpx.post(
                f"{gateway_url}/cart/items",
                json={"productId": KNOWN_PRODUCT_ID, "quantity": 2},
                headers=auth_headers(cart_user_token),
            )
            assert add_response.status_code == 200

            # Read via internal endpoint directly.
            internal_response = httpx.get(
                f"{CART_DIRECT_URL}/internal/cart/{user_id}"
            )
            assert internal_response.status_code == 200, (
                f"Expected 200 from internal endpoint but got "
                f"{internal_response.status_code}: {internal_response.text}"
            )
            internal_body = internal_response.json()
            assert internal_body["userId"] == user_id
            assert len(internal_body["items"]) == 1
            assert internal_body["items"][0]["productId"] == KNOWN_PRODUCT_ID
            assert internal_body["items"][0]["quantity"] == 2

            # Cleanup.
            httpx.delete(f"{gateway_url}/cart", headers=auth_headers(cart_user_token))

        def test_response_shape_matches_cart_response_record(self) -> None:
            """
            The internal endpoint returns the same CartResponse shape as the
            public endpoint: userId, items, totalAmount, updatedAt.
            """
            unknown_user = f"test-shape-{uuid.uuid4().hex[:8]}"
            response = httpx.get(f"{CART_DIRECT_URL}/internal/cart/{unknown_user}")

            assert response.status_code == 200
            body = response.json()
            for field in ("userId", "items", "totalAmount", "updatedAt"):
                assert field in body, (
                    f"Field '{field}' missing from internal CartResponse: {body}"
                )


# ===========================================================================
# Cross-cutting: ErrorResponse shape contract
# ===========================================================================

class TestErrorResponseShape:
    """
    Verify that error responses from the GlobalExceptionHandler conform to the
    ErrorResponse record: { status: int, error: str, message: str, timestamp: str }.
    """

    def test_404_error_response_has_required_fields(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        A 404 triggered by ProductNotFoundException must include all ErrorResponse fields.
        """
        response = httpx.put(
            f"{gateway_url}/cart/items/{NONEXISTENT_PRODUCT_ID}",
            json={"quantity": 1},
            headers=auth_headers(cart_user_token),
        )
        assert response.status_code == 404
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 404 response: {body}"
            )
        assert body["status"] == 404
        assert body["error"] == "Not Found"
        assert "timestamp" in body  # ISO-8601 string from Instant.now()

    def test_400_error_response_has_required_fields(
        self, gateway_url: str, cart_user_token: str
    ) -> None:
        """
        A 400 triggered by MethodArgumentNotValidException must include all
        ErrorResponse fields. The message field contains the first violated
        constraint in the format "fieldName: constraint message".
        """
        response = httpx.post(
            f"{gateway_url}/cart/items",
            json={"quantity": -1},  # missing productId (@NotNull) and negative quantity (@Min(1))
            headers=auth_headers(cart_user_token),
        )
        assert response.status_code == 400
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 400 response: {body}"
            )
        assert body["status"] == 400
        assert body["error"] == "Bad Request"
        # The message is the first field error, e.g. "productId: must not be null"
        assert ":" in body["message"], (
            f"Expected 'field: message' format in error message, got: {body['message']}"
        )
