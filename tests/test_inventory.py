"""
Inventory Service — integration tests
======================================
All gateway-routed requests target http://localhost:8080 which routes:
  /inventory/**  →  inventory-service at localhost:8086 (prefixed to /api/v1/inventory/**)

NOTE — gateway routing gap:
  The gateway predicate is Path=/inventory/** which matches /inventory/<something>
  but NOT the bare /inventory path. GET /inventory (getAllStock) may return a 404
  from the gateway rather than the service. TestGetAllStock is marked xfail for this.
  Fix: add "Path=/inventory, /inventory/**" to the gateway route.

Gateway auth behaviour:
  The gateway does NOT enforce auth on /inventory/** routes — all inventory
  endpoints are public (no Bearer token required).

Kafka flow tests:
  These tests produce Kafka events directly to simulate upstream services and
  verify state changes by polling the REST layer. They require kafka-python
  (pip install kafka-python) and a reachable Kafka broker.

Prerequisites:
  - Full stack running: gateway, auth-service, inventory-service, postgres, kafka.
  - Shared conftest.py fixtures (gateway_url) must be available.

Run:
  pytest tests/test_inventory.py -v

Environment variables:
  GATEWAY_URL           — override gateway base URL (default: http://localhost:8080)
  KAFKA_BOOTSTRAP       — override Kafka broker address (default: localhost:9092)
"""

import json
import os
import random
import time
import uuid

import httpx
import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")

TOPIC_ORDER_EVENTS = "order-events"
TOPIC_PAYMENT_EVENTS = "payment-events"

# A Long ID guaranteed not to exist in inventory
NONEXISTENT_PRODUCT_ID = 999_999_999


def _unique_product_id() -> int:
    """Return a random Long product ID to avoid test collisions."""
    return random.randint(100_000, 999_999_998)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_product(gateway_url: str, product_id: int, name: str, qty: int) -> dict:
    """POST /inventory/seed — create or add stock for a product."""
    response = httpx.post(
        f"{gateway_url}/inventory/seed",
        json={"productId": product_id, "productName": name, "quantity": qty},
    )
    assert response.status_code == 200, (
        f"Seed failed ({response.status_code}): {response.text}"
    )
    return response.json()


def _get_stock(gateway_url: str, product_id: int) -> dict:
    """GET /inventory/{productId} — return parsed InventoryResponse."""
    response = httpx.get(f"{gateway_url}/inventory/{product_id}")
    assert response.status_code == 200, (
        f"Get stock failed ({response.status_code}): {response.text}"
    )
    return response.json()


def _produce_kafka_event(topic: str, payload: dict) -> None:
    """
    Produce a single JSON message to the given Kafka topic.
    Skips the test if kafka-python is not installed or Kafka is unreachable.
    """
    try:
        from kafka import KafkaProducer
    except ImportError:
        pytest.skip("kafka-python not installed — skipping Kafka flow test")

    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            request_timeout_ms=5_000,
        )
        producer.send(topic, key=payload.get("correlationId"), value=payload)
        producer.flush(timeout=10)
        producer.close()
    except Exception as exc:
        pytest.skip(f"Kafka unreachable — skipping Kafka flow test: {exc}")


def _poll_until(
    check_fn,
    timeout: float = 10.0,
    interval: float = 0.5,
    description: str = "condition",
) -> None:
    """Repeatedly call check_fn() until it returns True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check_fn():
            return
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for: {description}")


# ===========================================================================
# POST /inventory/seed — create or add stock
# ===========================================================================

class TestSeedStock:
    """POST /inventory/seed via API Gateway — no auth required."""

    def test_seed_creates_new_inventory_entry_returns_200(
        self, gateway_url: str
    ) -> None:
        """
        Seeding a brand-new productId creates an inventory row and returns 200
        with all required InventoryResponse fields.
        Expected shape: { productId, productName, totalStock, available, reserved }
        """
        product_id = _unique_product_id()
        response = httpx.post(
            f"{gateway_url}/inventory/seed",
            json={"productId": product_id, "productName": "Test Widget", "quantity": 50},
        )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["productId"] == product_id
        assert body["productName"] == "Test Widget"
        assert body["totalStock"] == 50
        assert body["available"] == 50
        assert body["reserved"] == 0

    def test_seed_same_product_twice_adds_stock_cumulatively(
        self, gateway_url: str
    ) -> None:
        """
        seedStock is ADDITIVE — seeding an existing productId adds the new
        quantity on top of existing stock, it does NOT replace it.
        First seed: 10. Second seed: 40. Expected: totalStock=50, available=50.
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Widget A", 10)

        response = httpx.post(
            f"{gateway_url}/inventory/seed",
            json={"productId": product_id, "productName": "Widget A", "quantity": 40},
        )

        assert response.status_code == 200, (
            f"Expected 200 on second seed but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["productId"] == product_id
        assert body["totalStock"] == 50, (
            f"Expected cumulative totalStock=50, got {body['totalStock']}"
        )
        assert body["available"] == 50, (
            f"Expected cumulative available=50, got {body['available']}"
        )

    def test_seed_zero_quantity_returns_200(self, gateway_url: str) -> None:
        """
        quantity has @Min(0) — zero is a valid value and must return 200.
        This allows seeding a product into the catalogue with no initial stock.
        """
        response = httpx.post(
            f"{gateway_url}/inventory/seed",
            json={"productId": _unique_product_id(), "productName": "Empty Stock", "quantity": 0},
        )

        assert response.status_code == 200, (
            f"Expected 200 for zero quantity but got {response.status_code}: {response.text}"
        )

    def test_seed_negative_quantity_returns_400(self, gateway_url: str) -> None:
        """Negative quantity violates @Min(0) → 400 Bad Request."""
        response = httpx.post(
            f"{gateway_url}/inventory/seed",
            json={"productId": _unique_product_id(), "productName": "Widget", "quantity": -5},
        )

        assert response.status_code == 400, (
            f"Expected 400 for negative quantity but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400

    def test_seed_missing_product_id_returns_400(self, gateway_url: str) -> None:
        """productId is @NotNull — omitting it triggers validation → 400."""
        response = httpx.post(
            f"{gateway_url}/inventory/seed",
            json={"productName": "No ID Product", "quantity": 10},
        )

        assert response.status_code == 400, (
            f"Expected 400 when productId is missing, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400

    def test_seed_empty_body_returns_400(self, gateway_url: str) -> None:
        """Empty JSON body fails all @NotNull / @NotBlank validations → 400."""
        response = httpx.post(f"{gateway_url}/inventory/seed", json={})

        assert response.status_code == 400, (
            f"Expected 400 for empty body but got {response.status_code}: {response.text}"
        )


# ===========================================================================
# GET /inventory/{productId} — fetch stock for one product
# ===========================================================================

class TestGetStock:
    """GET /inventory/{productId} via API Gateway — no auth required."""

    def test_happy_path_returns_200_with_inventory_response(
        self, gateway_url: str
    ) -> None:
        """
        A productId that was seeded returns 200 with a well-formed InventoryResponse.
        Fields: productId, productName, totalStock, available, reserved.
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Gadget B", 30)

        response = httpx.get(f"{gateway_url}/inventory/{product_id}")

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        for field in ("productId", "productName", "totalStock", "available", "reserved"):
            assert field in body, f"Required field '{field}' missing: {body}"
        assert body["productId"] == product_id
        assert body["available"] == 30
        assert body["reserved"] == 0

    def test_nonexistent_product_returns_404(self, gateway_url: str) -> None:
        """
        A productId with no inventory row triggers ProductNotFoundException → 404.
        ErrorResponse shape: { status, error, message, timestamp }
        """
        response = httpx.get(f"{gateway_url}/inventory/{NONEXISTENT_PRODUCT_ID}")

        assert response.status_code == 404, (
            f"Expected 404 for unknown product but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 404
        assert "Not Found" in body.get("error", ""), (
            f"Expected 'Not Found' in error field: {body}"
        )

    def test_non_numeric_product_id_returns_400(self, gateway_url: str) -> None:
        """
        productId is @PathVariable Long — passing a non-numeric value triggers
        MethodArgumentTypeMismatchException → 400 Bad Request.
        """
        response = httpx.get(f"{gateway_url}/inventory/not-a-number")

        assert response.status_code == 400, (
            f"Expected 400 for non-numeric productId but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400

    def test_response_shape_has_all_required_fields(self, gateway_url: str) -> None:
        """InventoryResponse must always contain all 5 fields."""
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Shape Test", 1)

        body = _get_stock(gateway_url, product_id)
        for field in ("productId", "productName", "totalStock", "available", "reserved"):
            assert field in body, f"Field '{field}' missing: {body}"


# ===========================================================================
# GET /inventory — list all stock entries
# ===========================================================================

class TestGetAllStock:
    """GET /inventory via API Gateway — no auth required."""

    def test_returns_200_with_list(self, gateway_url: str) -> None:
        """
        GET /inventory returns 200 with a JSON array.
        After seeding at least one product the list must be non-empty.
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "List Product", 5)

        response = httpx.get(f"{gateway_url}/inventory")

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert isinstance(body, list), f"Expected a JSON array, got: {type(body)}"
        assert len(body) >= 1, "Expected at least one inventory entry after seeding"

    def test_each_entry_has_inventory_response_shape(self, gateway_url: str) -> None:
        """Every item in the list must conform to the InventoryResponse shape."""
        _seed_product(gateway_url, _unique_product_id(), "Shape Check", 10)

        response = httpx.get(f"{gateway_url}/inventory")
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        for entry in body:
            for field in ("productId", "productName", "totalStock", "available", "reserved"):
                assert field in entry, (
                    f"Field '{field}' missing from list entry: {entry}"
                )


# ===========================================================================
# PUT /inventory/{productId}/adjust — restock or shrink
# ===========================================================================

class TestAdjustStock:
    """PUT /inventory/{productId}/adjust via API Gateway — no auth required."""

    def test_positive_delta_increases_available_and_total_stock(
        self, gateway_url: str
    ) -> None:
        """
        A positive quantityDelta restocks the product — both totalStock and
        available increase by that delta (reserved is unchanged).
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Restock Me", 10)

        response = httpx.put(
            f"{gateway_url}/inventory/{product_id}/adjust",
            json={"quantityDelta": 20},
        )

        assert response.status_code == 200, (
            f"Expected 200 on restock but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["available"] == 30, (
            f"Expected available=30 after +20 restock, got {body['available']}"
        )
        assert body["totalStock"] == 30, (
            f"Expected totalStock=30 after +20 restock, got {body['totalStock']}"
        )

    def test_negative_delta_decreases_available_and_total_stock(
        self, gateway_url: str
    ) -> None:
        """A negative quantityDelta shrinks stock (e.g. write-off)."""
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Shrink Me", 20)

        response = httpx.put(
            f"{gateway_url}/inventory/{product_id}/adjust",
            json={"quantityDelta": -5},
        )

        assert response.status_code == 200, (
            f"Expected 200 on shrink but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["available"] == 15, (
            f"Expected available=15 after -5 shrink, got {body['available']}"
        )

    def test_shrink_below_zero_returns_409(self, gateway_url: str) -> None:
        """
        Adjusting stock so available would go negative must raise
        IllegalStateException → 409 Conflict.
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Deplete Me", 5)

        response = httpx.put(
            f"{gateway_url}/inventory/{product_id}/adjust",
            json={"quantityDelta": -100},
        )

        assert response.status_code == 409, (
            f"Expected 409 when trying to go negative, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 409

    def test_adjust_nonexistent_product_returns_404(
        self, gateway_url: str
    ) -> None:
        """Adjusting stock for a productId with no inventory row → 404."""
        response = httpx.put(
            f"{gateway_url}/inventory/{NONEXISTENT_PRODUCT_ID}/adjust",
            json={"quantityDelta": 10},
        )

        assert response.status_code == 404, (
            f"Expected 404 for unknown product but got {response.status_code}: {response.text}"
        )

    def test_missing_quantity_delta_returns_400(
        self, gateway_url: str
    ) -> None:
        """
        quantityDelta is a primitive int. Omitting it from JSON causes Jackson to
        attempt to unbox null into int → HttpMessageNotReadableException → 400.
        (Primitive fields cannot accept null during deserialization.)
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Missing Delta", 10)

        response = httpx.put(
            f"{gateway_url}/inventory/{product_id}/adjust",
            json={},
        )

        assert response.status_code == 400, (
            f"Expected 400 for missing quantityDelta (null→int unbox fails), "
            f"got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("status") == 400


# ===========================================================================
# Saga — Happy Path: OrderCreated → INVENTORY_RESERVED
# ===========================================================================

class TestSagaHappyPath:
    """
    Produce an OrderCreatedEvent to order-events, then poll the REST layer
    to verify that stock was reserved (available decreased, reserved increased).

    OrderCreatedEvent fields (must match Java record):
      type, correlationId, orderId (Long), userId (Integer),
      items (list of {productId (Long), quantity, price}), totalAmount, timestamp
    """

    def test_order_created_event_reserves_stock(self, gateway_url: str) -> None:
        """
        GIVEN product seeded with 50 units
        WHEN  ORDER_CREATED arrives requesting 3 units
        THEN  available drops to 47 and reserved rises to 3
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Saga Product", 50)

        correlation_id = str(uuid.uuid4())
        order_id = random.randint(1, 999_999)

        _produce_kafka_event(
            TOPIC_ORDER_EVENTS,
            {
                "type": "ORDER_CREATED",
                "correlationId": correlation_id,
                "orderId": order_id,
                "userId": random.randint(1, 9999),
                "items": [
                    {
                        "productId": product_id,
                        "quantity": 3,
                        "price": "9.99",
                    }
                ],
                "totalAmount": "29.97",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["available"] == 47,
            timeout=15.0,
            description=f"available to drop to 47 for product {product_id}",
        )

        stock = _get_stock(gateway_url, product_id)
        assert stock["available"] == 47, (
            f"Expected available=47 after reservation, got {stock['available']}"
        )
        assert stock["reserved"] == 3, (
            f"Expected reserved=3 after reservation, got {stock['reserved']}"
        )

    def test_multi_item_order_reserves_all_items_atomically(
        self, gateway_url: str
    ) -> None:
        """
        GIVEN two products with sufficient stock
        WHEN  a single ORDER_CREATED event requests units from both
        THEN  both products are reserved — all-or-nothing
        """
        product_a = _unique_product_id()
        product_b = _unique_product_id()
        _seed_product(gateway_url, product_a, "Atomic A", 20)
        _seed_product(gateway_url, product_b, "Atomic B", 20)

        correlation_id = str(uuid.uuid4())

        _produce_kafka_event(
            TOPIC_ORDER_EVENTS,
            {
                "type": "ORDER_CREATED",
                "correlationId": correlation_id,
                "orderId": random.randint(1, 999_999),
                "userId": random.randint(1, 9999),
                "items": [
                    {"productId": product_a, "quantity": 5, "price": "1.00"},
                    {"productId": product_b, "quantity": 7, "price": "2.00"},
                ],
                "totalAmount": "19.00",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        _poll_until(
            lambda: _get_stock(gateway_url, product_a)["available"] == 15,
            timeout=15.0,
            description="product A available to drop to 15",
        )

        stock_a = _get_stock(gateway_url, product_a)
        stock_b = _get_stock(gateway_url, product_b)
        assert stock_a["available"] == 15 and stock_a["reserved"] == 5, (
            f"product A: expected available=15 reserved=5, got {stock_a}"
        )
        assert stock_b["available"] == 13 and stock_b["reserved"] == 7, (
            f"product B: expected available=13 reserved=7, got {stock_b}"
        )


# ===========================================================================
# Saga — Failure Path: OrderCreated with insufficient stock
# ===========================================================================

class TestSagaInsufficientStock:
    """
    When an ORDER_CREATED event requests more stock than available,
    the service must NOT partially reserve anything — all-or-nothing enforcement.
    """

    def test_insufficient_stock_does_not_mutate_inventory(
        self, gateway_url: str
    ) -> None:
        """
        GIVEN product with only 2 available units
        WHEN  order requests 10 units
        THEN  available remains 2 and reserved remains 0 (no partial reservation)
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Low Stock", 2)

        _produce_kafka_event(
            TOPIC_ORDER_EVENTS,
            {
                "type": "ORDER_CREATED",
                "correlationId": str(uuid.uuid4()),
                "orderId": random.randint(1, 999_999),
                "userId": random.randint(1, 9999),
                "items": [{"productId": product_id, "quantity": 10, "price": "5.00"}],
                "totalAmount": "50.00",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        time.sleep(3)
        stock = _get_stock(gateway_url, product_id)
        assert stock["available"] == 2, (
            f"Stock must not be mutated on insufficient stock: available={stock['available']}"
        )
        assert stock["reserved"] == 0, (
            f"Reserved must remain 0 on failed reservation: reserved={stock['reserved']}"
        )

    def test_partial_insufficient_stock_does_not_reserve_any_item(
        self, gateway_url: str
    ) -> None:
        """
        GIVEN product A has enough stock but product B does not
        WHEN  a multi-item order is placed
        THEN  product A is also NOT reserved — all-or-nothing enforcement.
        Critical guard against silent partial reservation corruption.
        """
        product_a = _unique_product_id()
        product_b = _unique_product_id()
        _seed_product(gateway_url, product_a, "Partial A", 100)
        _seed_product(gateway_url, product_b, "Partial B", 1)

        _produce_kafka_event(
            TOPIC_ORDER_EVENTS,
            {
                "type": "ORDER_CREATED",
                "correlationId": str(uuid.uuid4()),
                "orderId": random.randint(1, 999_999),
                "userId": random.randint(1, 9999),
                "items": [
                    {"productId": product_a, "quantity": 5, "price": "1.00"},
                    {"productId": product_b, "quantity": 50, "price": "1.00"},
                ],
                "totalAmount": "55.00",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        time.sleep(3)
        stock_a = _get_stock(gateway_url, product_a)
        stock_b = _get_stock(gateway_url, product_b)

        assert stock_a["available"] == 100, (
            f"Product A must NOT be partially reserved. Got available={stock_a['available']}"
        )
        assert stock_a["reserved"] == 0
        assert stock_b["available"] == 1
        assert stock_b["reserved"] == 0


# ===========================================================================
# Saga — Compensation: PaymentFailed → stock released back
# ===========================================================================

class TestSagaCompensation:
    """
    Produce a PAYMENT_FAILED event after a successful reservation and verify
    that the stock is released back to available.

    PaymentEvent fields (must match Java record): type, correlationId, reason
    """

    def test_payment_failed_releases_reserved_stock(
        self, gateway_url: str
    ) -> None:
        """
        GIVEN stock is reserved (available=47, reserved=3)
        WHEN  PAYMENT_FAILED event arrives with the same correlationId
        THEN  available returns to 50 and reserved returns to 0
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Compensate Me", 50)

        correlation_id = str(uuid.uuid4())
        order_id = random.randint(1, 999_999)

        # Step 1: reserve stock via ORDER_CREATED
        _produce_kafka_event(
            TOPIC_ORDER_EVENTS,
            {
                "type": "ORDER_CREATED",
                "correlationId": correlation_id,
                "orderId": order_id,
                "userId": random.randint(1, 9999),
                "items": [{"productId": product_id, "quantity": 3, "price": "10.00"}],
                "totalAmount": "30.00",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["reserved"] == 3,
            timeout=15.0,
            description="reserved to become 3",
        )

        # Step 2: simulate payment failure
        _produce_kafka_event(
            TOPIC_PAYMENT_EVENTS,
            {
                "type": "PAYMENT_FAILED",
                "correlationId": correlation_id,
                "reason": "Simulated failure in test",
            },
        )

        # Step 3: poll until compensation completes
        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["reserved"] == 0,
            timeout=15.0,
            description="reserved to return to 0 after compensation",
        )

        stock = _get_stock(gateway_url, product_id)
        assert stock["available"] == 50, (
            f"Expected available=50 after compensation, got {stock['available']}"
        )
        assert stock["reserved"] == 0, (
            f"Expected reserved=0 after compensation, got {stock['reserved']}"
        )


# ===========================================================================
# Saga — Confirmation: PaymentSuccess → reservation confirmed
# ===========================================================================

class TestSagaConfirmation:
    """
    Produce a PAYMENT_SUCCESS event after a successful reservation and verify
    that the reservation is confirmed (reserved drops, available stays at
    post-reservation level — stock permanently sold).
    """

    def test_payment_success_confirms_reservation(self, gateway_url: str) -> None:
        """
        GIVEN stock is reserved (available=47, reserved=3)
        WHEN  PAYMENT_SUCCESS event arrives
        THEN  reserved drops to 0, available stays at 47 (permanently sold)
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Confirm Me", 50)

        correlation_id = str(uuid.uuid4())
        order_id = random.randint(1, 999_999)

        # Step 1: reserve
        _produce_kafka_event(
            TOPIC_ORDER_EVENTS,
            {
                "type": "ORDER_CREATED",
                "correlationId": correlation_id,
                "orderId": order_id,
                "userId": random.randint(1, 9999),
                "items": [{"productId": product_id, "quantity": 3, "price": "10.00"}],
                "totalAmount": "30.00",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["reserved"] == 3,
            timeout=15.0,
            description="reserved to become 3 before confirming",
        )

        # Step 2: simulate payment success
        _produce_kafka_event(
            TOPIC_PAYMENT_EVENTS,
            {
                "type": "PAYMENT_SUCCESS",
                "correlationId": correlation_id,
                "reason": None,
            },
        )

        # Step 3: reserved should drop; available must NOT go back up
        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["reserved"] == 0,
            timeout=15.0,
            description="reserved to drop to 0 after confirmation",
        )

        stock = _get_stock(gateway_url, product_id)
        assert stock["reserved"] == 0, (
            f"Expected reserved=0 after confirmation, got {stock['reserved']}"
        )
        assert stock["available"] == 47, (
            f"Expected available=47 (permanently sold), got {stock['available']}"
        )


# ===========================================================================
# Idempotency — duplicate Kafka events
# ===========================================================================

class TestIdempotency:
    """
    NOTE: InventoryService has NO ProcessedEvent deduplication table.
    Compensation and confirmation are implicitly idempotent because they query
    reservations by (correlationId, RESERVED) status — a second run finds nothing
    to act on. However, a duplicate ORDER_CREATED event WILL double-reserve.

    The reservation test below is marked xfail to document this gap.
    Compensation/confirmation idempotency tests pass because the status
    transition acts as a natural guard.
    """

    @pytest.mark.xfail(
        reason=(
            "No ProcessedEvent deduplication for ORDER_CREATED — "
            "duplicate events will double-reserve stock"
        ),
        strict=True,
    )
    def test_duplicate_order_created_event_does_not_double_reserve(
        self, gateway_url: str
    ) -> None:
        """
        GIVEN product seeded with 100 units
        WHEN  same ORDER_CREATED (same correlationId) produced twice
        THEN  only 5 units reserved — idempotency guard fires on second delivery.
        Currently FAILS because no deduplication is implemented.
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Idempotent Product", 100)

        correlation_id = str(uuid.uuid4())
        event = {
            "type": "ORDER_CREATED",
            "correlationId": correlation_id,
            "orderId": random.randint(1, 999_999),
            "userId": random.randint(1, 9999),
            "items": [{"productId": product_id, "quantity": 5, "price": "1.00"}],
            "totalAmount": "5.00",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        _produce_kafka_event(TOPIC_ORDER_EVENTS, event)
        _produce_kafka_event(TOPIC_ORDER_EVENTS, event)

        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["reserved"] >= 5,
            timeout=15.0,
            description="reserved to reach at least 5 after first event",
        )

        time.sleep(3)

        stock = _get_stock(gateway_url, product_id)
        assert stock["reserved"] == 5, (
            f"Expected reserved=5 (idempotency), got {stock['reserved']} — "
            f"duplicate event was processed twice!"
        )
        assert stock["available"] == 95, (
            f"Expected available=95, got {stock['available']}"
        )

    def test_duplicate_payment_failed_does_not_double_release(
        self, gateway_url: str
    ) -> None:
        """
        PAYMENT_FAILED idempotency is implicit: releaseReservation queries
        by (correlationId, RESERVED) status. After the first release the status
        becomes RELEASED, so a second event finds nothing to release.
        Stock must stay at 50 — not become 53 (double release).
        """
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Idempotent Release", 50)

        correlation_id = str(uuid.uuid4())

        _produce_kafka_event(
            TOPIC_ORDER_EVENTS,
            {
                "type": "ORDER_CREATED",
                "correlationId": correlation_id,
                "orderId": random.randint(1, 999_999),
                "userId": random.randint(1, 9999),
                "items": [{"productId": product_id, "quantity": 3, "price": "1.00"}],
                "totalAmount": "3.00",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["reserved"] == 3,
            timeout=15.0,
            description="reserved to become 3",
        )

        payment_event = {
            "type": "PAYMENT_FAILED",
            "correlationId": correlation_id,
            "reason": "test failure",
        }
        _produce_kafka_event(TOPIC_PAYMENT_EVENTS, payment_event)
        _produce_kafka_event(TOPIC_PAYMENT_EVENTS, payment_event)

        _poll_until(
            lambda: _get_stock(gateway_url, product_id)["reserved"] == 0,
            timeout=15.0,
            description="reserved to return to 0 after first PAYMENT_FAILED",
        )

        time.sleep(2)

        stock = _get_stock(gateway_url, product_id)
        assert stock["available"] == 50, (
            f"Expected available=50 after idempotent release, got {stock['available']} "
            f"(double release would give 53)"
        )
        assert stock["reserved"] == 0


# ===========================================================================
# Cross-cutting: ErrorResponse shape contract
# ===========================================================================

class TestErrorResponseShape:
    """
    Verify all error responses from GlobalExceptionHandler conform to:
    { status: int, error: str, message: str, timestamp: str }
    """

    def test_404_error_has_all_required_fields(self, gateway_url: str) -> None:
        """ProductNotFoundException → 404 must include status, error, message, timestamp."""
        response = httpx.get(f"{gateway_url}/inventory/{NONEXISTENT_PRODUCT_ID}")

        assert response.status_code == 404
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 404: {body}"
            )
        assert body["status"] == 404
        assert body["error"] == "Not Found"

    def test_400_error_has_all_required_fields(self, gateway_url: str) -> None:
        """MethodArgumentNotValidException → 400 must include status, error, message, timestamp."""
        response = httpx.post(
            f"{gateway_url}/inventory/seed",
            json={"productName": "No ID", "quantity": -1},
        )

        assert response.status_code == 400
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 400: {body}"
            )
        assert body["status"] == 400
        assert body["error"] == "Bad Request"
        assert ":" in body["message"], (
            f"Expected 'field: message' format, got: {body['message']}"
        )

    def test_409_error_has_all_required_fields(self, gateway_url: str) -> None:
        """IllegalStateException → 409 must include status, error, message, timestamp."""
        product_id = _unique_product_id()
        _seed_product(gateway_url, product_id, "Conflict Test", 1)

        response = httpx.put(
            f"{gateway_url}/inventory/{product_id}/adjust",
            json={"quantityDelta": -9999},
        )

        assert response.status_code == 409
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from 409: {body}"
            )
        assert body["status"] == 409
        assert body["error"] == "Conflict"

    def test_400_type_mismatch_has_all_required_fields(self, gateway_url: str) -> None:
        """MethodArgumentTypeMismatchException → 400 must include all ErrorResponse fields."""
        response = httpx.get(f"{gateway_url}/inventory/not-a-long")

        assert response.status_code == 400
        body = response.json()
        for field in ("status", "error", "message", "timestamp"):
            assert field in body, (
                f"ErrorResponse field '{field}' missing from type-mismatch 400: {body}"
            )
        assert body["status"] == 400
        assert body["error"] == "Bad Request"
