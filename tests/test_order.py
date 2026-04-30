"""
Order Service — integration tests
==================================
All gateway-routed requests target http://localhost:8080 which routes:
  /orders/**  →  PrefixPath=/api/v1  →  order-service at localhost:8085

Gateway auth behaviour (JWTAuthenticationFilter):
  /orders/** IS in the gateway's requiresAuth list:
    requiresAuth = path.startsWith("/orders") || ...
  Therefore:
    - Missing or invalid Bearer token → 401 returned by the GATEWAY (service never reached).
    - Valid Bearer token → gateway injects X-User-Id and X-User-Role headers → service handles.

  This is different from /cart/** routes, where the gateway does not enforce auth and
  the service itself returns 400 for a missing X-User-Id header. For /orders/**, a
  missing or invalid token is stopped at the gateway with 401.

Order Service auth behaviour:
  OrderController reads @RequestHeader("X-User-Id") on every endpoint. The gateway
  injects this header for any valid JWT (not just protected routes). Because the gateway
  already enforces 401 for /orders/**, by the time the service sees a request it will
  always have a valid X-User-Id header.

Internal endpoint behaviour:
  GET /api/v1/internal/orders/{orderId} is served directly at port 8085.
  InternalOrderController uses getOrderById() with no userId filter — it is intended
  for inter-service reads and requires no authentication.
  The api-gateway has no route for /internal/**, so requests via the gateway at
  /internal/orders/{orderId} return 404 from the gateway itself.
  Tests for the internal endpoint hit port 8085 directly.

Error response shape (GlobalExceptionHandler → ErrorResponse record):
  { status: int, error: str, message: str, timestamp: str (ISO-8601) }

Order response shape (OrderResponse record):
  { id, userId, correlationId, status, totalAmount, shippingAddress, items, createdAt, updatedAt }
  items: [{ productId, productName, price, quantity }]

Order statuses: PENDING, INVENTORY_RESERVED, CONFIRMED, FAILED, CANCELLED

Pre-conditions for POST /orders:
  - The session user must have at least one item in their cart (cart-service at port 8084).
  - Add via POST http://localhost:8080/cart/items: { "productId": <id>, "quantity": <n> }
  - An empty cart triggers EmptyCartException → 422 Unprocessable Entity.
  - Kafka must be running for the OrderCreatedEvent to be published after creation.
    If Kafka is not running, POST /orders may fail with a 500 (producer error).
    Set SKIP_KAFKA_DEPENDENT_TESTS=true to skip tests that require Kafka.

Prerequisites:
  - Full stack running: gateway, auth-service, order-service, cart-service,
    product-catalog, postgres, redis, kafka.
  - The shared conftest.py fixtures (gateway_url, auth_tokens, registered_user)
    must be on sys.path (run from the project root: pytest tests/ services/order-service/).

Run:
  pytest tests/test_order.py -v

Environment variables:
  GATEWAY_URL                  — override gateway base URL (default: http://localhost:8080)
  ORDER_DIRECT_URL             — override direct order-service URL
                                 (default: http://localhost:8085/api/v1)
  KNOWN_PRODUCT_ID             — integer product ID that exists in the product-catalog;
                                 required for tests that seed the cart before creating an
                                 order. If not set, those tests are skipped.
  SKIP_KAFKA_DEPENDENT_TESTS   — set to "true" to skip tests that publish Kafka events
                                 (POST /orders happy-path). Useful when Kafka is not running.
"""

import os
import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
ORDER_DIRECT_URL = os.environ.get("ORDER_DIRECT_URL", "http://localhost:8085/api/v1")

# Product ID known to exist in the catalog — required for cart seeding before order creation.
_KNOWN_PRODUCT_ID_ENV = os.environ.get("KNOWN_PRODUCT_ID")
KNOWN_PRODUCT_ID: int | None = int(_KNOWN_PRODUCT_ID_ENV) if _KNOWN_PRODUCT_ID_ENV else None

# A numeric ID guaranteed not to match any order in the database.
NONEXISTENT_ORDER_ID = 999_999_999_999

SKIP_KAFKA = os.environ.get("SKIP_KAFKA_DEPENDENT_TESTS", "").lower() == "true"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_headers(access_token: str) -> dict:
    """Build an Authorization header dict from a bearer token."""
    return {"Authorization": f"Bearer {access_token}"}


def _require_known_product() -> None:
    """Skip a test if KNOWN_PRODUCT_ID env var is not set."""
    if KNOWN_PRODUCT_ID is None:
        pytest.skip(
            "KNOWN_PRODUCT_ID env var is not set. "
            "Set it to a valid product ID from the catalog to run this test."
        )


def _skip_if_kafka_disabled() -> None:
    """Skip tests that require Kafka when SKIP_KAFKA_DEPENDENT_TESTS=true."""
    if SKIP_KAFKA:
        pytest.skip(
            "SKIP_KAFKA_DEPENDENT_TESTS=true — skipping test that publishes a Kafka event."
        )


def _seed_cart(gateway_url: str, token: str, product_id: int, quantity: int = 2) -> None:
    """
    Clear the user's cart then add one item, asserting each step succeeds.
    This ensures POST /orders always starts from a known non-empty cart state.
    A failure here means the infrastructure is misconfigured, not the order service.
    """
    clear = httpx.delete(f"{gateway_url}/cart", headers=auth_headers(token))
    assert clear.status_code in (200, 204), (
        f"Cart clear failed ({clear.status_code}): {clear.text}"
    )
    add = httpx.post(
        f"{gateway_url}/cart/items",
        json={"productId": product_id, "quantity": quantity},
        headers=auth_headers(token),
    )
    assert add.status_code == 200, (
        f"Cart seed failed ({add.status_code}): {add.text}"
    )


def _clear_cart(gateway_url: str, token: str) -> None:
    """Best-effort cart clear used in test setup. Does not assert success."""
    httpx.delete(f"{gateway_url}/cart", headers=auth_headers(token))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def order_token(auth_tokens: dict) -> str:
    """Readable alias for the session access token used across order tests."""
    return auth_tokens["access_token"]


# ===========================================================================
# POST /orders — create order from cart
# ===========================================================================

class TestCreateOrder:
    """
    POST /orders via API Gateway.
    Gateway route: /orders/** → PrefixPath=/api/v1 → order-service at :8085.
    Auth: enforced by gateway — missing/invalid token → 401 before the service is reached.
    Pre-condition: cart must be non-empty, otherwise the service returns 422.
    Side effect: order-service clears the user's cart after successful creation.
    Kafka: OrderCreatedEvent is published on success — Kafka must be running unless
           SKIP_KAFKA_DEPENDENT_TESTS=true.
    """

    def test_happy_path_creates_order_returns_201(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        With a non-empty cart and a valid JWT, POST /orders must return 201 Created
        with a full OrderResponse. The order status must be PENDING immediately after
        creation (Saga events drive further transitions asynchronously).
        """
        _require_known_product()
        _skip_if_kafka_disabled()

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=2)

        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "123 Main St, Springfield, IL 62701"},
            headers=auth_headers(order_token),
        )

        assert response.status_code == 201, (
            f"Expected 201 Created but got {response.status_code}: {response.text}"
        )
        body = response.json()

        # All OrderResponse record fields must be present.
        for field in ("id", "userId", "correlationId", "status", "totalAmount",
                      "shippingAddress", "items", "createdAt", "updatedAt"):
            assert field in body, (
                f"Required field '{field}' missing from OrderResponse: {body}"
            )

        assert body["status"] == "PENDING", (
            f"Newly created order must have status PENDING, got: {body['status']}"
        )
        assert body["shippingAddress"] == "123 Main St, Springfield, IL 62701", (
            f"shippingAddress does not match request body: {body['shippingAddress']}"
        )
        assert isinstance(body["items"], list) and len(body["items"]) > 0, (
            f"Expected non-empty items list in OrderResponse: {body['items']}"
        )
        assert float(body["totalAmount"]) > 0, (
            f"totalAmount should be positive for a non-empty cart: {body['totalAmount']}"
        )
        assert body["correlationId"] is not None and len(body["correlationId"]) > 0, (
            "correlationId must be a non-empty UUID string"
        )

    def test_order_items_match_cart_contents(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        Each OrderItemResponse in the returned items list must have the fields
        productId, productName, price, quantity, and the values must match what
        was seeded into the cart (productId and quantity are directly verifiable).
        """
        _require_known_product()
        _skip_if_kafka_disabled()

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=3)

        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "456 Oak Ave, Portland, OR 97201"},
            headers=auth_headers(order_token),
        )

        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert len(body["items"]) >= 1, (
            f"Order must contain at least one item: {body['items']}"
        )
        item = body["items"][0]
        for field in ("productId", "productName", "price", "quantity"):
            assert field in item, (
                f"OrderItemResponse field '{field}' missing: {item}"
            )
        assert item["productId"] == KNOWN_PRODUCT_ID, (
            f"Expected productId {KNOWN_PRODUCT_ID}, got {item['productId']}"
        )
        assert item["quantity"] == 3, (
            f"Expected quantity 3 (seeded in cart), got {item['quantity']}"
        )
        assert float(item["price"]) > 0, (
            f"Item price must be positive: {item['price']}"
        )

    def test_cart_is_cleared_after_successful_order(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        OrderService.createOrder() calls cartClient.clearCart() after saving the order.
        A subsequent GET /cart must return an empty items list.
        This validates the cart-clearing side-effect that prevents double-ordering.
        """
        _require_known_product()
        _skip_if_kafka_disabled()

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=1)

        create_response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "789 Elm St, Chicago, IL 60601"},
            headers=auth_headers(order_token),
        )
        assert create_response.status_code == 201, (
            f"Order creation failed ({create_response.status_code}): {create_response.text}"
        )

        cart_response = httpx.get(
            f"{gateway_url}/cart",
            headers=auth_headers(order_token),
        )
        assert cart_response.status_code == 200, (
            f"GET /cart after order failed ({cart_response.status_code}): {cart_response.text}"
        )
        cart_items = cart_response.json().get("items", [])
        assert cart_items == [], (
            f"Cart should be empty after order creation, but items remain: {cart_items}"
        )

    def test_second_order_gets_unique_id_and_correlation_id(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        Each order must receive a unique database id and a unique correlationId (UUID).
        The correlationId is used by downstream Saga events to locate the correct order.
        Two successive orders must not share either identifier.
        """
        _require_known_product()
        _skip_if_kafka_disabled()

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=1)
        r1 = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "Order One St"},
            headers=auth_headers(order_token),
        )
        assert r1.status_code == 201

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=1)
        r2 = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "Order Two Ave"},
            headers=auth_headers(order_token),
        )
        assert r2.status_code == 201

        body1, body2 = r1.json(), r2.json()
        assert body1["id"] != body2["id"], (
            f"Two consecutive orders must have different ids: both got {body1['id']}"
        )
        assert body1["correlationId"] != body2["correlationId"], (
            f"Two consecutive orders must have different correlationIds: "
            f"both got {body1['correlationId']}"
        )

    def test_empty_cart_returns_422(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        POSTing /orders when the cart is empty triggers EmptyCartException in the service.
        GlobalExceptionHandler maps this to 422 Unprocessable Entity.
        ErrorResponse: { status: 422, error: "Unprocessable Entity",
                         message: "Cannot create order from an empty cart", timestamp }
        """
        _clear_cart(gateway_url, order_token)

        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "123 Main St, Springfield, IL 62701"},
            headers=auth_headers(order_token),
        )

        assert response.status_code == 422, (
            f"Expected 422 Unprocessable Entity for empty cart but got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 422, (
            f"ErrorResponse.status must be 422: {body}"
        )
        assert body.get("error") == "Unprocessable Entity", (
            f"ErrorResponse.error must be 'Unprocessable Entity': {body}"
        )
        assert "empty cart" in body.get("message", "").lower(), (
            f"Expected 'empty cart' in error message, got: {body.get('message')}"
        )

    def test_missing_shipping_address_returns_400(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        shippingAddress is annotated @NotBlank on CreateOrderRequest. Omitting it
        triggers MethodArgumentNotValidException → 400 Bad Request.
        GlobalExceptionHandler formats the message as "fieldName: constraint message".
        """
        response = httpx.post(
            f"{gateway_url}/orders",
            json={},
            headers=auth_headers(order_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 when shippingAddress is missing but got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400
        assert body.get("error") == "Bad Request", (
            f"ErrorResponse.error must be 'Bad Request': {body}"
        )
        assert "shippingAddress" in body.get("message", ""), (
            f"Expected 'shippingAddress' in validation error message, got: {body.get('message')}"
        )

    def test_blank_shipping_address_returns_400(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        shippingAddress is @NotBlank — a whitespace-only string passes JSON
        deserialization but fails the constraint → 400 Bad Request.
        """
        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "   "},
            headers=auth_headers(order_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 for blank shippingAddress but got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400
        assert body.get("error") == "Bad Request"

    def test_null_shipping_address_returns_400(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        Explicitly sending null for shippingAddress also fails @NotBlank → 400.
        (@NotBlank implicitly includes @NotNull behaviour.)
        """
        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": None},
            headers=auth_headers(order_token),
        )

        assert response.status_code == 400, (
            f"Expected 400 for null shippingAddress but got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400

    def test_no_token_returns_401(self, gateway_url: str) -> None:
        """
        /orders/** is in the gateway's requiresAuth list. A request with no
        Authorization header is rejected by JWTAuthenticationFilter → 401.
        The order-service is never reached.
        """
        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "123 Main St, Springfield, IL 62701"},
        )

        assert response.status_code == 401, (
            f"Expected 401 (gateway enforces auth on /orders/**) but got "
            f"{response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_401(self, gateway_url: str) -> None:
        """
        An invalid Bearer token fails jwtService.isTokenValid() in the gateway filter
        → 401. The order-service is never reached.
        """
        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "123 Main St, Springfield, IL 62701"},
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"},
        )

        assert response.status_code == 401, (
            f"Expected 401 for invalid JWT on POST /orders but got "
            f"{response.status_code}: {response.text}"
        )

    def test_malformed_bearer_prefix_returns_401(self, gateway_url: str) -> None:
        """
        The gateway only extracts a token from headers that start with 'Bearer '.
        A malformed prefix (e.g., 'Token <jwt>') means no token is extracted,
        which is treated as missing → 401.
        """
        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "123 Main St, Springfield, IL 62701"},
            headers={"Authorization": "Token some.valid.looking.token"},
        )

        assert response.status_code == 401, (
            f"Expected 401 for malformed Bearer prefix but got "
            f"{response.status_code}: {response.text}"
        )


# ===========================================================================
# GET /orders — list user's orders
# ===========================================================================

class TestListOrders:
    """
    GET /orders via API Gateway.
    Returns a JSON array of OrderResponse objects owned by the authenticated user.
    An empty list is returned when the user has no orders (not 404).
    The service scopes results to the userId injected by the gateway from the JWT.
    Auth: gateway enforces 401 for missing/invalid tokens.
    """

    def test_returns_200_with_json_array(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        A valid JWT always returns 200 with a JSON array. The array may be empty
        if the user has placed no orders, or non-empty from prior test runs.
        The response body must be a list (not an object).
        """
        response = httpx.get(
            f"{gateway_url}/orders",
            headers=auth_headers(order_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 for GET /orders but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert isinstance(body, list), (
            f"GET /orders must return a JSON array, got {type(body).__name__}: {body}"
        )

    def test_list_items_have_correct_shape(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        Each element in the returned array must conform to the OrderResponse record
        shape. This test only makes assertions on individual items if orders exist;
        it passes vacuously on an empty list.
        """
        response = httpx.get(
            f"{gateway_url}/orders",
            headers=auth_headers(order_token),
        )
        assert response.status_code == 200
        body = response.json()

        for order in body:
            for field in ("id", "userId", "correlationId", "status", "totalAmount",
                          "shippingAddress", "items", "createdAt", "updatedAt"):
                assert field in order, (
                    f"OrderResponse field '{field}' missing from list element: {order}"
                )
            assert isinstance(order["items"], list), (
                f"'items' must be a list within each OrderResponse: {order['items']}"
            )

    def test_created_order_appears_in_list(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        After creating an order via POST /orders, GET /orders must include it.
        This verifies the list endpoint queries the same data that was persisted.
        """
        _require_known_product()
        _skip_if_kafka_disabled()

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=1)
        create_response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "List Test Blvd, Austin, TX 78701"},
            headers=auth_headers(order_token),
        )
        assert create_response.status_code == 201, (
            f"Order creation for list test failed: {create_response.text}"
        )
        created_id = create_response.json()["id"]

        list_response = httpx.get(
            f"{gateway_url}/orders",
            headers=auth_headers(order_token),
        )
        assert list_response.status_code == 200
        order_ids = [o["id"] for o in list_response.json()]
        assert created_id in order_ids, (
            f"Created order {created_id} not found in list: {order_ids}"
        )

    def test_user_only_sees_own_orders(self, gateway_url: str) -> None:
        """
        GET /orders must only return orders belonging to the authenticated user.
        We register a second fresh user and verify they see an empty list,
        confirming the service correctly scopes queries by the X-User-Id header
        injected from the JWT.
        """
        second_id = uuid.uuid4().hex[:12]
        reg = httpx.post(
            f"{gateway_url}/auth/register",
            json={
                "firstName": "Isolated",
                "lastName": "User",
                "email": f"isolated.{second_id}@shopnow-test.com",
                "password": "SecurePass1!",
            },
        )
        assert reg.status_code == 200, f"Second user registration failed: {reg.text}"

        login = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": f"isolated.{second_id}@shopnow-test.com",
                "password": "SecurePass1!",
            },
        )
        assert login.status_code == 200
        second_token = login.json()["access_token"]

        response = httpx.get(
            f"{gateway_url}/orders",
            headers=auth_headers(second_token),
        )
        assert response.status_code == 200
        assert response.json() == [], (
            f"Brand-new user should have no orders, got: {response.json()}"
        )

    def test_no_token_returns_401(self, gateway_url: str) -> None:
        """
        GET /orders without an Authorization header → gateway enforces auth → 401.
        """
        response = httpx.get(f"{gateway_url}/orders")

        assert response.status_code == 401, (
            f"Expected 401 for unauthenticated GET /orders but got "
            f"{response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_401(self, gateway_url: str) -> None:
        """
        GET /orders with an invalid JWT → gateway filter rejects it → 401.
        """
        response = httpx.get(
            f"{gateway_url}/orders",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"},
        )

        assert response.status_code == 401, (
            f"Expected 401 for invalid JWT on GET /orders but got "
            f"{response.status_code}: {response.text}"
        )


# ===========================================================================
# GET /orders/{orderId} — get order by ID
# ===========================================================================

class TestGetOrderById:
    """
    GET /orders/{orderId} via API Gateway.
    The service implementation filters by both orderId AND userId:
        orderRepository.findById(orderId).filter(o -> o.getUserId().equals(userId))
    If the order belongs to a different user it is filtered out and the service
    throws OrderNotFoundException → 404. This prevents information leakage (403
    would confirm the order exists).
    Auth: gateway enforces 401 for missing/invalid tokens.
    """

    @pytest.fixture(scope="class")
    def created_order(self, gateway_url: str, order_token: str) -> dict:
        """
        Create a real order for the session user and return its full response body.
        Tests in this class that need a real order depend on this fixture.
        The whole class is skipped if KNOWN_PRODUCT_ID or Kafka are unavailable.
        """
        _require_known_product()
        _skip_if_kafka_disabled()

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=1)
        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "789 Elm St, Chicago, IL 60601"},
            headers=auth_headers(order_token),
        )
        assert response.status_code == 201, (
            f"Order creation fixture failed ({response.status_code}): {response.text}"
        )
        return response.json()

    def test_happy_path_returns_200_with_order(
        self, gateway_url: str, order_token: str, created_order: dict
    ) -> None:
        """
        GET /orders/{orderId} for an order owned by the authenticated user returns
        200 with the full OrderResponse for that specific order.
        """
        order_id = created_order["id"]

        response = httpx.get(
            f"{gateway_url}/orders/{order_id}",
            headers=auth_headers(order_token),
        )

        assert response.status_code == 200, (
            f"Expected 200 for own order but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["id"] == order_id, (
            f"Returned order id {body['id']} does not match requested id {order_id}"
        )
        for field in ("id", "userId", "correlationId", "status", "totalAmount",
                      "shippingAddress", "items", "createdAt", "updatedAt"):
            assert field in body, (
                f"OrderResponse field '{field}' missing: {body}"
            )

    def test_response_items_are_populated(
        self, gateway_url: str, order_token: str, created_order: dict
    ) -> None:
        """
        The items list in the fetched order must be non-empty and each item must
        include all OrderItemResponse fields: productId, productName, price, quantity.
        """
        response = httpx.get(
            f"{gateway_url}/orders/{created_order['id']}",
            headers=auth_headers(order_token),
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) >= 1, (
            f"Expected at least one item in fetched order: {body['items']}"
        )
        item = body["items"][0]
        for field in ("productId", "productName", "price", "quantity"):
            assert field in item, (
                f"OrderItemResponse field '{field}' missing: {item}"
            )

    def test_shipping_address_matches_what_was_submitted(
        self, gateway_url: str, order_token: str, created_order: dict
    ) -> None:
        """
        The shippingAddress in the fetched order must exactly match what was
        submitted in CreateOrderRequest. The service stores and returns it verbatim.
        """
        response = httpx.get(
            f"{gateway_url}/orders/{created_order['id']}",
            headers=auth_headers(order_token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["shippingAddress"] == created_order["shippingAddress"], (
            f"shippingAddress mismatch: expected '{created_order['shippingAddress']}', "
            f"got '{body['shippingAddress']}'"
        )

    def test_nonexistent_order_id_returns_404(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        Requesting an orderId that does not exist raises OrderNotFoundException
        → 404 Not Found.
        ErrorResponse message follows the pattern: "Order not found: <id>"
        """
        response = httpx.get(
            f"{gateway_url}/orders/{NONEXISTENT_ORDER_ID}",
            headers=auth_headers(order_token),
        )

        assert response.status_code == 404, (
            f"Expected 404 for non-existent order but got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 404
        assert body.get("error") == "Not Found", (
            f"Expected error='Not Found', got: {body}"
        )
        assert str(NONEXISTENT_ORDER_ID) in body.get("message", ""), (
            f"Expected order ID in error message, got: {body.get('message')}"
        )

    def test_another_users_order_returns_404(
        self, gateway_url: str, order_token: str, created_order: dict
    ) -> None:
        """
        The service filters by userId after looking up by orderId. Requesting a
        valid orderId while authenticated as a different user returns 404, not 403.
        This prevents leaking whether an order with a given ID exists.

        Service code:
          orderRepository.findById(orderId)
              .filter(o -> o.getUserId().equals(userId))
              .orElseThrow(() -> new OrderNotFoundException(orderId));
        """
        second_id = uuid.uuid4().hex[:12]
        reg = httpx.post(
            f"{gateway_url}/auth/register",
            json={
                "firstName": "Another",
                "lastName": "User",
                "email": f"another.{second_id}@shopnow-test.com",
                "password": "SecurePass1!",
            },
        )
        assert reg.status_code == 200, f"Second user registration failed: {reg.text}"
        login = httpx.post(
            f"{gateway_url}/auth/login",
            json={
                "email": f"another.{second_id}@shopnow-test.com",
                "password": "SecurePass1!",
            },
        )
        assert login.status_code == 200
        other_token = login.json()["access_token"]

        response = httpx.get(
            f"{gateway_url}/orders/{created_order['id']}",
            headers=auth_headers(other_token),
        )

        assert response.status_code == 404, (
            f"Expected 404 when accessing another user's order but got "
            f"{response.status_code}: {response.text}. "
            f"The service returns 404 (not 403) to avoid leaking order existence."
        )

    def test_no_token_returns_401(self, gateway_url: str) -> None:
        """
        GET /orders/{orderId} without an Authorization header → gateway returns 401.
        """
        response = httpx.get(f"{gateway_url}/orders/{NONEXISTENT_ORDER_ID}")

        assert response.status_code == 401, (
            f"Expected 401 for unauthenticated GET /orders/{{id}} but got "
            f"{response.status_code}: {response.text}"
        )

    def test_invalid_token_returns_401(self, gateway_url: str) -> None:
        """
        GET /orders/{orderId} with an invalid JWT → gateway filter rejects → 401.
        """
        response = httpx.get(
            f"{gateway_url}/orders/{NONEXISTENT_ORDER_ID}",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"},
        )

        assert response.status_code == 401, (
            f"Expected 401 for invalid JWT on GET /orders/{{id}} but got "
            f"{response.status_code}: {response.text}"
        )

    def test_non_numeric_order_id_returns_400_or_404(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        orderId is declared as Long in the controller path variable. Passing a
        non-numeric value ('abc') causes Spring to fail path variable binding before
        the service logic is reached → 400 (MethodArgumentTypeMismatchException).
        Some gateway configurations may return 404 if the path does not match any
        route — either is acceptable here.
        """
        response = httpx.get(
            f"{gateway_url}/orders/not-a-number",
            headers=auth_headers(order_token),
        )

        assert response.status_code in (400, 404), (
            f"Expected 400 (type mismatch) or 404 (path unmatched) for non-numeric "
            f"orderId but got {response.status_code}: {response.text}"
        )


# ===========================================================================
# GET /api/v1/internal/orders/{orderId}
# Direct call to order-service at port 8085 — NOT via the gateway.
# ===========================================================================

class TestInternalOrderEndpoint:
    """
    GET /api/v1/internal/orders/{orderId} — direct service call, no JWT required.

    Served by InternalOrderController using orderService.getOrderById() (no userId
    filter). This is an intentionally open endpoint for inter-service reads (e.g.,
    inventory-service or payment-service looking up an order by correlationId).

    The api-gateway has no route for /internal/**, so:
      - Via gateway (/internal/orders/{id}) → 404 from the gateway.
      - Direct to port 8085 (/api/v1/internal/orders/{id}) → service responds normally.
    """

    @pytest.fixture(scope="class")
    def direct_order_id(self, gateway_url: str, order_token: str) -> int:
        """
        Create a real order via the gateway and return its id for internal endpoint tests.
        Skips the class if KNOWN_PRODUCT_ID or Kafka is unavailable.
        """
        _require_known_product()
        _skip_if_kafka_disabled()

        _seed_cart(gateway_url, order_token, KNOWN_PRODUCT_ID, quantity=1)
        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "321 Pine Rd, Seattle, WA 98101"},
            headers=auth_headers(order_token),
        )
        assert response.status_code == 201, (
            f"Order creation fixture for internal tests failed "
            f"({response.status_code}): {response.text}"
        )
        return response.json()["id"]

    class TestGatewayDoesNotExposeInternalRoute:
        """The gateway must not route /internal/orders/* to the order-service."""

        def test_internal_orders_via_gateway_with_token_returns_404(
            self, gateway_url: str, auth_tokens: dict
        ) -> None:
            """
            /internal/orders/{id} has no matching gateway route. The gateway returns
            404 — the order-service is never reached, even with a valid token.
            """
            response = httpx.get(
                f"{gateway_url}/internal/orders/1",
                headers=auth_headers(auth_tokens["access_token"]),
            )
            assert response.status_code == 404, (
                f"Expected 404 (no gateway route for /internal/orders/**) but got "
                f"{response.status_code}: {response.text}"
            )

        def test_internal_orders_via_gateway_without_token_returns_404(
            self, gateway_url: str
        ) -> None:
            """
            Even without a token the gateway returns 404 for /internal/orders/**.
            If this starts returning 401, it means a route was added to the gateway
            with auth protection — that would be a misconfiguration of the internal path.
            """
            response = httpx.get(f"{gateway_url}/internal/orders/1")
            assert response.status_code == 404, (
                f"Expected 404 (no gateway route) but got {response.status_code}: {response.text}"
            )

    class TestDirectServiceCall:
        """Call the order-service on port 8085 directly, bypassing the gateway."""

        def test_returns_200_for_existing_order(
            self, direct_order_id: int
        ) -> None:
            """
            GET /api/v1/internal/orders/{orderId} returns 200 with the full
            OrderResponse for any existing order. No Authorization header is needed.
            """
            response = httpx.get(f"{ORDER_DIRECT_URL}/internal/orders/{direct_order_id}")

            assert response.status_code == 200, (
                f"Expected 200 from internal endpoint but got "
                f"{response.status_code}: {response.text}"
            )
            body = response.json()
            assert body["id"] == direct_order_id, (
                f"Returned id {body['id']} does not match requested id {direct_order_id}"
            )

        def test_response_shape_matches_order_response_record(
            self, direct_order_id: int
        ) -> None:
            """
            The internal endpoint returns the same OrderResponse shape as the public
            endpoint: id, userId, correlationId, status, totalAmount, shippingAddress,
            items, createdAt, updatedAt.
            """
            response = httpx.get(f"{ORDER_DIRECT_URL}/internal/orders/{direct_order_id}")
            assert response.status_code == 200
            body = response.json()
            for field in ("id", "userId", "correlationId", "status", "totalAmount",
                          "shippingAddress", "items", "createdAt", "updatedAt"):
                assert field in body, (
                    f"Field '{field}' missing from internal OrderResponse: {body}"
                )

        def test_no_auth_header_still_returns_200(
            self, direct_order_id: int
        ) -> None:
            """
            The internal endpoint has no authentication requirement. Sending a request
            without any Authorization header must succeed (200) for a valid order id.
            This confirms the endpoint is intentionally open for inter-service use.
            """
            response = httpx.get(
                f"{ORDER_DIRECT_URL}/internal/orders/{direct_order_id}"
                # No headers at all — explicitly testing unauthenticated access is allowed.
            )

            assert response.status_code == 200, (
                f"Internal endpoint should not require auth but got "
                f"{response.status_code}: {response.text}"
            )

        def test_no_user_scope_filter_returns_any_users_order(
            self, direct_order_id: int
        ) -> None:
            """
            Unlike the public GET /orders/{orderId} which applies .filter(userId),
            InternalOrderController.getOrder() calls getOrderById() with no userId
            scope. The response must include the userId field but must not filter on it.
            This validates the intentional design difference between public and internal.
            """
            response = httpx.get(f"{ORDER_DIRECT_URL}/internal/orders/{direct_order_id}")
            assert response.status_code == 200, (
                f"Internal endpoint must return any order regardless of who is asking: "
                f"{response.status_code}: {response.text}"
            )
            body = response.json()
            # userId is present in the response (informational) but not used as a filter.
            assert "userId" in body, (
                f"Internal OrderResponse must include the userId field: {body}"
            )

        def test_nonexistent_order_returns_404(self) -> None:
            """
            GET /api/v1/internal/orders/{nonExistentId} — no order found →
            OrderNotFoundException → 404, even on the direct internal endpoint.
            ErrorResponse: { status: 404, error: "Not Found",
                             message: "Order not found: <id>", timestamp }
            """
            response = httpx.get(
                f"{ORDER_DIRECT_URL}/internal/orders/{NONEXISTENT_ORDER_ID}"
            )

            assert response.status_code == 404, (
                f"Expected 404 for non-existent order on internal endpoint but got "
                f"{response.status_code}: {response.text}"
            )
            body = response.json()
            assert body.get("status") == 404
            assert body.get("error") == "Not Found", (
                f"Expected error='Not Found': {body}"
            )
            assert str(NONEXISTENT_ORDER_ID) in body.get("message", ""), (
                f"Expected order ID in error message: {body.get('message')}"
            )


# ===========================================================================
# Cross-cutting: ErrorResponse shape contract
# ===========================================================================

class TestErrorResponseShape:
    """
    Verify that all error responses produced by GlobalExceptionHandler conform to
    the ErrorResponse record shape:
      { status: int, error: str, message: str, timestamp: str (ISO-8601) }

    This contract is shared across all handlers in the file:
      - OrderNotFoundException      → 404
      - EmptyCartException          → 422
      - MethodArgumentNotValidException → 400
      - Exception (catch-all)       → 500
    """

    def test_404_error_response_has_all_required_fields(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        A 404 from OrderNotFoundException must include all ErrorResponse fields.
        The message follows the pattern from the exception constructor:
          "Order not found: <id>"
        """
        response = httpx.get(
            f"{gateway_url}/orders/{NONEXISTENT_ORDER_ID}",
            headers=auth_headers(order_token),
        )
        assert response.status_code == 404
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 404 response: {body}"
            )
        assert body["status"] == 404
        assert body["error"] == "Not Found"
        assert isinstance(body["timestamp"], str) and len(body["timestamp"]) > 0, (
            f"timestamp must be a non-empty ISO-8601 string: {body.get('timestamp')}"
        )

    def test_400_error_response_has_all_required_fields(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        A 400 from MethodArgumentNotValidException must include all ErrorResponse fields.
        GlobalExceptionHandler extracts the first field error and formats the message as:
          "fieldName: defaultMessage"
        """
        response = httpx.post(
            f"{gateway_url}/orders",
            json={},  # shippingAddress is @NotBlank → validation failure
            headers=auth_headers(order_token),
        )
        assert response.status_code == 400
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 400 response: {body}"
            )
        assert body["status"] == 400
        assert body["error"] == "Bad Request"
        # GlobalExceptionHandler formats as "field: message" via getField() + getDefaultMessage()
        assert ":" in body["message"], (
            f"Expected 'field: message' format in error message, got: {body['message']}"
        )
        assert isinstance(body["timestamp"], str) and len(body["timestamp"]) > 0

    def test_422_error_response_has_all_required_fields(
        self, gateway_url: str, order_token: str
    ) -> None:
        """
        A 422 from EmptyCartException must include all ErrorResponse fields.
        The message is the one set in EmptyCartException:
          "Cannot create order from an empty cart"
        """
        _clear_cart(gateway_url, order_token)

        response = httpx.post(
            f"{gateway_url}/orders",
            json={"shippingAddress": "Error Shape Test St"},
            headers=auth_headers(order_token),
        )
        assert response.status_code == 422, (
            f"Expected 422 for empty cart but got {response.status_code}: {response.text}"
        )
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 422 response: {body}"
            )
        assert body["status"] == 422
        assert body["error"] == "Unprocessable Entity"
        assert "Cannot create order from an empty cart" == body.get("message"), (
            f"Unexpected 422 message: {body.get('message')}"
        )
        assert isinstance(body["timestamp"], str) and len(body["timestamp"]) > 0
