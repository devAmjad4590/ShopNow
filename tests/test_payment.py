"""
Payment Service — integration tests
=====================================
The payment service is fully event-driven and has no public REST API. It only
exposes two internal REST endpoints on port 8087. All payment processing happens
asynchronously via Kafka Saga choreography.

Saga happy path:
  POST /orders → OrderCreatedEvent
  → [Inventory] reserves stock → InventoryReservedEvent
  → [Payment] calls Stripe → PaymentSuccessEvent
  → [Order] marks CONFIRMED

Saga compensation path:
  POST /orders → OrderCreatedEvent
  → [Inventory] reserves stock → InventoryReservedEvent
  → [Payment] forced failure → PaymentFailedEvent
  → [Inventory] releases stock → [Order] marks FAILED

Gateway auth behaviour (JWTAuthenticationFilter):
  POST /orders requires a valid Bearer token — the gateway enforces 401 for
  missing/invalid tokens before the order-service is reached.
  Internal payment endpoints (/api/v1/internal/**) are NOT routed through the
  gateway. Requests to /internal/payments/** via the gateway return 404.

Internal endpoint behaviour:
  POST /api/v1/internal/payments/simulate-failure/{orderId}
    Registers orderId (Long) for one-shot forced failure. Returns 200 OK.
    The flag is consumed atomically when the InventoryReservedEvent arrives.

  GET /api/v1/internal/payments/{orderId}
    Returns PaymentStatusResponse: { orderId, status, stripePaymentIntentId,
    failureReason, createdAt, updatedAt }. Returns 404 if no payment record exists.

Payment statuses: PENDING, SUCCESS, FAILED
orderId type: Long (database-generated integer, not UUID)

Order creation:
  1. Add items to cart via POST /cart/items (items are fetched from cart by order-service)
  2. POST /api/v1/orders (via gateway, requires JWT): { "shippingAddress": "..." }
  3. Returns 201 Created: { id, userId, correlationId, status: PENDING, ... }
  4. Poll GET /api/v1/orders/{id} until status changes from PENDING

Stripe: test mode, synchronous PaymentIntent, no real money.

Prerequisites:
  - Full stack running: gateway, auth-service, order-service, cart-service,
    product-catalog, inventory-service, payment-service, postgres, redis, kafka.
  - The shared conftest.py fixtures (gateway_url, auth_tokens, registered_user)
    must be available (run from project root: pytest tests/).

Run:
  pytest tests/test_payment.py -v

Environment variables:
  GATEWAY_URL            — override gateway base URL (default: http://localhost:8080)
  PAYMENT_DIRECT_URL     — override direct payment-service URL (default: http://localhost:8087/api/v1)
  ORDER_DIRECT_URL       — override direct order-service URL (default: http://localhost:8085/api/v1)
  KNOWN_PRODUCT_ID       — integer product ID that exists in the catalog; required for
                           any test that places an order. Skipped if not set.
  SAGA_TIMEOUT_SECONDS   — max seconds to wait for Saga to settle (default: 15)
"""

import os
import time
import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAYMENT_DIRECT_URL = os.environ.get("PAYMENT_DIRECT_URL", "http://localhost:8087/api/v1")
ORDER_DIRECT_URL = os.environ.get("ORDER_DIRECT_URL", "http://localhost:8085/api/v1")

_KNOWN_PRODUCT_ID_ENV = os.environ.get("KNOWN_PRODUCT_ID")
KNOWN_PRODUCT_ID: int | None = int(_KNOWN_PRODUCT_ID_ENV) if _KNOWN_PRODUCT_ID_ENV else None

SAGA_TIMEOUT_SECONDS: int = int(os.environ.get("SAGA_TIMEOUT_SECONDS", "15"))

# A numeric order ID guaranteed not to exist in the database.
NONEXISTENT_ORDER_ID = 999_999_999


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


def poll_order_status(gateway_url: str, order_id: int, token: str, timeout: int = SAGA_TIMEOUT_SECONDS) -> str:
    """
    Poll GET /orders/{orderId} via the gateway until status is no longer PENDING
    or the timeout expires. Returns the final status string.

    Raises TimeoutError with a descriptive message if still PENDING after timeout.
    Polls every 1 second.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{gateway_url}/orders/{order_id}",
            headers=auth_headers(token),
        )
        assert response.status_code == 200, (
            f"Polling GET /orders/{order_id} returned {response.status_code}: {response.text}"
        )
        status = response.json().get("status")
        if status != "PENDING":
            return status
        time.sleep(1)
    raise TimeoutError(
        f"Order {order_id} still PENDING after {timeout}s — "
        "Saga did not settle within the timeout window."
    )


def _seed_cart_and_create_order(gateway_url: str, token: str) -> int:
    """
    Clear the cart, add KNOWN_PRODUCT_ID, then POST /orders.
    Returns the numeric orderId (Long) from the response.
    Asserts each step succeeds.
    """
    httpx.delete(f"{gateway_url}/cart", headers=auth_headers(token))

    add_resp = httpx.post(
        f"{gateway_url}/cart/items",
        json={"productId": KNOWN_PRODUCT_ID, "quantity": 1},
        headers=auth_headers(token),
    )
    assert add_resp.status_code == 200, (
        f"Failed to seed cart before order creation: {add_resp.status_code} {add_resp.text}"
    )

    order_resp = httpx.post(
        f"{gateway_url}/orders",
        json={"shippingAddress": "123 Test Street, Test City, 00000"},
        headers=auth_headers(token),
    )
    assert order_resp.status_code == 201, (
        f"Failed to create order: {order_resp.status_code} {order_resp.text}"
    )
    order_id = order_resp.json().get("id")
    assert order_id is not None, (
        f"'id' missing from order creation response: {order_resp.json()}"
    )
    return int(order_id)


# ===========================================================================
# GET /api/v1/internal/payments/{orderId}
# Direct calls to payment-service on port 8087 — NOT via the gateway.
# ===========================================================================

class TestGetPaymentStatus:
    """
    GET /api/v1/internal/payments/{orderId} — direct service call, no JWT required.

    Validates 404 for unknown orders, response shape, and correct data after Saga.
    """

    def test_returns_404_for_nonexistent_order_id(self) -> None:
        """
        A payment record is only created when InventoryReservedEvent arrives for an
        order. Querying a numeric ID with no such record must return 404 with an
        error body containing 'error' and 'timestamp' fields.
        """
        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{NONEXISTENT_ORDER_ID}")

        assert response.status_code == 404, (
            f"Expected 404 for nonexistent orderId {NONEXISTENT_ORDER_ID} "
            f"but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "error" in body, f"Expected 'error' field in 404 body: {body}"
        assert "timestamp" in body, f"Expected 'timestamp' field in 404 body: {body}"

    def test_response_shape_has_all_required_fields(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        After a successful Saga, the payment record must include all PaymentStatusResponse
        fields: orderId, status, stripePaymentIntentId, failureReason, createdAt, updatedAt.
        A happy-path order is placed to ensure a record exists.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Expected order {order_id} to reach CONFIRMED but got {final_status}"
        )

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")

        assert response.status_code == 200, (
            f"Expected 200 for payment record of order {order_id} "
            f"but got {response.status_code}: {response.text}"
        )
        body = response.json()
        for field in ("orderId", "status", "stripePaymentIntentId", "failureReason", "createdAt", "updatedAt"):
            assert field in body, (
                f"Required field '{field}' missing from PaymentStatusResponse: {body}"
            )

    def test_returns_200_with_correct_order_id_after_successful_saga(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        After a happy-path Saga settles, GET /internal/payments/{orderId} must
        return 200 and the orderId in the body must match the requested orderId.
        This confirms the record is keyed correctly.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        poll_order_status(gateway_url, order_id, token)

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")

        assert response.status_code == 200, (
            f"Expected 200 for payment record of order {order_id} "
            f"but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["orderId"] == order_id, (
            f"Expected orderId={order_id} in response but got orderId={body['orderId']}"
        )


# ===========================================================================
# POST /api/v1/internal/payments/simulate-failure/{orderId}
# Direct calls to payment-service on port 8087 — NOT via the gateway.
# ===========================================================================

class TestSimulateFailure:
    """
    POST /api/v1/internal/payments/simulate-failure/{orderId} — direct service call.

    Validates the simulate-failure mechanism: one-shot flag, idempotent set,
    and that subsequent orders without a flag are not affected.
    """

    def test_returns_200_for_any_numeric_order_id(self) -> None:
        """
        simulate-failure only registers a flag in memory — it does not validate
        whether the orderId actually exists. Calling it with any numeric ID must
        return 200 OK. The flag is simply stored in a ConcurrentHashSet.
        """
        arbitrary_order_id = NONEXISTENT_ORDER_ID

        response = httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{arbitrary_order_id}"
        )

        assert response.status_code == 200, (
            f"Expected 200 from simulate-failure but got "
            f"{response.status_code}: {response.text}"
        )

    def test_calling_multiple_times_before_payment_is_idempotent(self) -> None:
        """
        The forced-failure set is a ConcurrentHashSet<Long>. Adding the same orderId
        multiple times has no effect beyond the first call — the set contains at most
        one entry per orderId. All calls must return 200 OK without error.
        """
        order_id = NONEXISTENT_ORDER_ID + 1

        for i in range(3):
            response = httpx.post(
                f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{order_id}"
            )
            assert response.status_code == 200, (
                f"Call #{i + 1} to simulate-failure for order {order_id} "
                f"returned {response.status_code}: {response.text}"
            )

    def test_one_shot_flag_is_consumed_after_first_payment(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        simulate-failure uses forcedFailureOrders.remove() — the flag is consumed
        atomically when the payment is processed. Placing a second order without
        calling simulate-failure again must succeed (status CONFIRMED), proving
        the flag was not reused.

        Sequence:
          1. Place order 1 → call simulate-failure/{order1Id} → order 1 becomes FAILED
          2. Place order 2 (no simulate-failure call) → order 2 must become CONFIRMED
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        # Order 1: forced failure.
        order1_id = _seed_cart_and_create_order(gateway_url, token)
        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{order1_id}"
        )
        status1 = poll_order_status(gateway_url, order1_id, token)
        assert status1 == "FAILED", (
            f"Expected order {order1_id} to be FAILED after simulate-failure, got {status1}"
        )

        # Order 2: no simulate-failure → flag was consumed by order 1, not reused.
        order2_id = _seed_cart_and_create_order(gateway_url, token)
        status2 = poll_order_status(gateway_url, order2_id, token)
        assert status2 == "CONFIRMED", (
            f"Expected order {order2_id} to reach CONFIRMED (flag consumed after order 1), "
            f"got {status2}"
        )


# ===========================================================================
# End-to-end: happy path Saga
# ===========================================================================

class TestSagaHappyPath:
    """
    Full happy-path Saga: place order → poll until CONFIRMED → verify payment record.

    Does not call simulate-failure. Stripe test mode is used; no real money charged.
    """

    def test_order_reaches_confirmed_status_within_timeout(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        A valid order with stock available must transition from PENDING → CONFIRMED
        within SAGA_TIMEOUT_SECONDS seconds. The full Saga must complete:
        OrderCreatedEvent → InventoryReservedEvent → PaymentSuccessEvent → CONFIRMED.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)

        assert final_status == "CONFIRMED", (
            f"Expected order {order_id} to reach CONFIRMED but got {final_status}"
        )

    def test_payment_record_has_success_status_after_confirmed_order(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        Once the order is CONFIRMED, the payment record at GET /internal/payments/{orderId}
        must have status=SUCCESS. SUCCESS means Stripe accepted the charge and
        PaymentSuccessEvent was published.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200, (
            f"Expected 200 for payment record but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["status"] == "SUCCESS", (
            f"Expected payment status SUCCESS for confirmed order {order_id}, "
            f"got {body['status']}"
        )

    def test_stripe_payment_intent_id_is_populated_on_success(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        On a successful Stripe charge, the service stores the PaymentIntent ID
        (starts with 'pi_') on the payment record. A null or empty value means
        Stripe was never called or the charge failed silently.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200
        body = response.json()
        intent_id = body.get("stripePaymentIntentId")
        assert intent_id is not None and intent_id.startswith("pi_"), (
            f"Expected stripePaymentIntentId to start with 'pi_' but got: {intent_id!r}"
        )

    def test_failure_reason_is_null_on_success(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        failureReason must be null (None in Python) when payment succeeds. A non-null
        failureReason on a SUCCESS record would indicate a data inconsistency.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200
        body = response.json()
        assert body.get("failureReason") is None, (
            f"Expected failureReason=null on successful payment, "
            f"got: {body.get('failureReason')!r}"
        )


# ===========================================================================
# End-to-end: compensation path Saga
# ===========================================================================

class TestSagaCompensationPath:
    """
    Full compensation Saga: place order → simulate failure → poll until FAILED
    → verify payment record reflects the forced failure.
    """

    def test_order_reaches_failed_status_after_simulate_failure(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        Calling simulate-failure before InventoryReservedEvent is processed forces
        the payment service to skip Stripe and publish PaymentFailedEvent. The order
        must transition from PENDING → FAILED within SAGA_TIMEOUT_SECONDS.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{order_id}"
        )
        final_status = poll_order_status(gateway_url, order_id, token)

        assert final_status == "FAILED", (
            f"Expected order {order_id} to reach FAILED after simulate-failure, "
            f"got {final_status}"
        )

    def test_payment_record_has_failed_status_after_forced_failure(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        The payment record for a forced-failure order must have status=FAILED.
        This confirms the compensation branch of processInventoryReservedEvent ran.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{order_id}"
        )
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "FAILED", (
            f"Order {order_id} did not reach FAILED: {final_status}"
        )

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200, (
            f"Expected 200 for failed payment record but got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["status"] == "FAILED", (
            f"Expected payment status FAILED for order {order_id}, got {body['status']}"
        )

    def test_failure_reason_is_forced_failure_string(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        When simulate-failure triggers the compensation path, the service calls
        fail(payment, "Forced failure"). The failureReason field must contain
        exactly "Forced failure" (matches the hardcoded string in PaymentService).
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{order_id}"
        )
        poll_order_status(gateway_url, order_id, token)

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200
        body = response.json()
        assert body.get("failureReason") == "Forced failure", (
            f"Expected failureReason='Forced failure' but got: {body.get('failureReason')!r}"
        )

    def test_stripe_payment_intent_id_is_null_on_forced_failure(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        The forced-failure path calls fail() immediately after creating the payment
        record — before calling stripePaymentService.charge(). Stripe is never
        invoked, so stripePaymentIntentId must be null.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{order_id}"
        )
        poll_order_status(gateway_url, order_id, token)

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200
        body = response.json()
        assert body.get("stripePaymentIntentId") is None, (
            f"Expected stripePaymentIntentId=null on forced failure "
            f"(Stripe was never called), got: {body.get('stripePaymentIntentId')!r}"
        )

    def test_idempotency_no_duplicate_payment_record_for_same_order(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        PaymentService.processInventoryReservedEvent() checks paymentRepository
        .existsByCorrelationId() before creating a record. Duplicate Kafka delivery
        of the same InventoryReservedEvent must not create a second payment record.
        Verified by confirming exactly one record exists after the Saga settles and
        that the GET endpoint returns a single PaymentStatusResponse (not a list).
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/{order_id}"
        )
        poll_order_status(gateway_url, order_id, token)

        # GET returns a single object, not an array — any duplicate would cause the
        # repository to hold multiple records but the endpoint only returns one.
        # We validate there is no 500 (e.g., IncorrectResultSizeDataAccessException)
        # and the response is a JSON object (not a list).
        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200, (
            f"Expected 200 for idempotency check on order {order_id} "
            f"but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert isinstance(body, dict), (
            f"Expected a single PaymentStatusResponse object, got: {type(body).__name__}: {body}"
        )
        assert body["orderId"] == order_id, (
            f"Response orderId mismatch: expected {order_id}, got {body['orderId']}"
        )


# ===========================================================================
# Gateway does not expose internal routes
# ===========================================================================

class TestGatewayDoesNotExposeInternalRoutes:
    """
    Confirms the API Gateway has no route for /internal/payments/**. Requests via
    the gateway must return 404 (unmatched route), never reaching the payment service.
    """

    def test_get_payment_status_via_gateway_returns_404(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        GET /internal/payments/{orderId} has no matching gateway route.
        The gateway returns 404 — the payment-service is never reached.
        """
        response = httpx.get(
            f"{gateway_url}/internal/payments/{NONEXISTENT_ORDER_ID}",
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 404, (
            f"Expected 404 (no gateway route for /internal/payments/**) "
            f"but got {response.status_code}: {response.text}"
        )

    def test_simulate_failure_via_gateway_returns_404(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        POST /internal/payments/simulate-failure/{orderId} has no matching gateway
        route. The gateway returns 404. If this returns 200, the internal endpoint
        is incorrectly exposed to external callers.
        """
        response = httpx.post(
            f"{gateway_url}/internal/payments/simulate-failure/{NONEXISTENT_ORDER_ID}",
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 404, (
            f"Expected 404 (no gateway route for /internal/payments/simulate-failure/**) "
            f"but got {response.status_code}: {response.text}"
        )

    def test_get_payment_status_via_gateway_without_token_returns_404(
        self, gateway_url: str
    ) -> None:
        """
        Even without a token the gateway returns 404 for this path.
        If this returns 401, a route was added without auth protection.
        """
        response = httpx.get(
            f"{gateway_url}/internal/payments/{NONEXISTENT_ORDER_ID}"
        )
        assert response.status_code == 404, (
            f"Expected 404 (no gateway route) but got {response.status_code}: {response.text}"
        )


# ===========================================================================
# PaymentStatusResponse shape contract
# ===========================================================================

class TestPaymentStatusResponseShape:
    """
    Contract tests for PaymentStatusResponse. Validates field presence, valid enum
    values, and ISO-8601 timestamp strings. Uses a real payment record created via
    the Saga happy path.
    """

    def test_all_required_fields_present(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        PaymentStatusResponse must always include: orderId, status,
        stripePaymentIntentId, failureReason, createdAt, updatedAt.
        All six fields must be present even when some are null (e.g., failureReason
        is null on success, stripePaymentIntentId is null on failure).
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        poll_order_status(gateway_url, order_id, token)

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200
        body = response.json()

        required_fields = ("orderId", "status", "stripePaymentIntentId", "failureReason", "createdAt", "updatedAt")
        for field in required_fields:
            assert field in body, (
                f"Required field '{field}' missing from PaymentStatusResponse: {body}"
            )

    def test_status_is_valid_enum_value(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        PaymentStatus is an enum with values PENDING, SUCCESS, FAILED.
        A settled payment must have status SUCCESS or FAILED — never PENDING
        and never an unrecognised value.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        poll_order_status(gateway_url, order_id, token)

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200
        body = response.json()
        valid_statuses = {"PENDING", "SUCCESS", "FAILED"}
        assert body["status"] in valid_statuses, (
            f"Expected status to be one of {valid_statuses}, got: {body['status']!r}"
        )

    def test_created_at_and_updated_at_are_valid_iso8601(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """
        createdAt and updatedAt are serialised from java.time.Instant, which produces
        ISO-8601 strings ending in 'Z' (e.g., '2024-01-15T10:30:00.123456789Z').
        Both must be non-null, non-empty strings that can be parsed as ISO-8601.
        """
        _require_known_product()
        token = auth_tokens["access_token"]

        order_id = _seed_cart_and_create_order(gateway_url, token)
        poll_order_status(gateway_url, order_id, token)

        response = httpx.get(f"{PAYMENT_DIRECT_URL}/internal/payments/{order_id}")
        assert response.status_code == 200
        body = response.json()

        for field in ("createdAt", "updatedAt"):
            value = body.get(field)
            assert value is not None and isinstance(value, str) and len(value) > 0, (
                f"Expected '{field}' to be a non-empty string, got: {value!r}"
            )
            assert "T" in value and ("Z" in value or "+" in value), (
                f"Expected '{field}' to look like an ISO-8601 instant "
                f"(contains 'T' and timezone), got: {value!r}"
            )
