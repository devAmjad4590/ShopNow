"""
Notification Service — integration tests
==========================================
The notification service is fully event-driven and has no public REST API. It has
no direct HTTP endpoints — all email dispatch happens asynchronously in response
to Kafka events produced by the Saga.

What we can verify externally:
  1. MailHog HTTP API (port 8025) — query the in-memory inbox to assert that emails
     were delivered after Saga events settle. MailHog exposes:
       GET /api/v2/messages         — list all messages
       DELETE /api/v2/messages      — clear inbox
       GET /api/v2/search?kind=to&query=<email>  — filter by recipient

  2. End-to-end Saga flows — place a real order, wait for Saga to settle, then
     confirm that the correct email landed in the MailHog inbox.

Saga happy path:
  POST /orders -> Saga settles CONFIRMED -> ORDER_CONFIRMED email sent to user

Saga compensation path:
  POST /orders + simulate-failure -> Saga settles FAILED -> ORDER_FAILED email sent to user

Architecture notes:
  - Notification service has NO database, NO REST endpoints, NO Kafka producers.
  - It only listens on: order-events (ORDER_CONFIRMED, ORDER_COMPENSATION)
  - The notification-service is NOT routed through the API Gateway.
  - MailHog web API runs at MAILHOG_URL (default: http://localhost:8025).

Prerequisites:
  - Full stack running: gateway, auth-service, order-service, cart-service,
    product-catalog, inventory-service, payment-service, notification-service,
    postgres, redis, kafka, mailhog.
  - The shared conftest.py fixtures (gateway_url, auth_tokens, registered_user)
    must be available (run from project root: pytest tests/).

Run:
  pytest tests/test_notification.py -v

Environment variables:
  GATEWAY_URL            — override gateway base URL (default: http://localhost:8080)
  PAYMENT_DIRECT_URL     — override direct payment-service URL (default: http://localhost:8087/api/v1)
  MAILHOG_URL            — override MailHog API URL (default: http://localhost:8025)
  KNOWN_PRODUCT_ID       — integer product ID that exists in the catalog; required for
                           any test that places an order. Skipped if not set.
  SAGA_TIMEOUT_SECONDS   — max seconds to wait for Saga to settle (default: 15)
  EMAIL_TIMEOUT_SECONDS  — max seconds to wait for email to arrive in MailHog (default: 10)
"""

import base64
import json
import os
import time

import httpx
import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAILHOG_URL = os.environ.get("MAILHOG_URL", "http://localhost:8025")
PAYMENT_DIRECT_URL = os.environ.get("PAYMENT_DIRECT_URL", "http://localhost:8087/api/v1")
INVENTORY_DIRECT_URL = os.environ.get("INVENTORY_DIRECT_URL", "http://localhost:8086/api/v1")

_KNOWN_PRODUCT_ID_ENV = os.environ.get("KNOWN_PRODUCT_ID")
KNOWN_PRODUCT_ID: int | None = int(_KNOWN_PRODUCT_ID_ENV) if _KNOWN_PRODUCT_ID_ENV else None

SAGA_TIMEOUT_SECONDS: int = int(os.environ.get("SAGA_TIMEOUT_SECONDS", "15"))
EMAIL_TIMEOUT_SECONDS: int = int(os.environ.get("EMAIL_TIMEOUT_SECONDS", "10"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_headers(access_token: str) -> dict:
    """Build an Authorization header dict from a bearer token."""
    return {"Authorization": f"Bearer {access_token}"}


def _get_user_id_from_token(token: str) -> int:
    """Decode JWT payload (no verification) and return the userId claim."""
    segment = token.split('.')[1]
    segment += '=' * (-len(segment) % 4)
    payload = json.loads(base64.b64decode(segment))
    return int(payload['userId'])


def _require_known_product() -> None:
    """Skip a test if KNOWN_PRODUCT_ID env var is not set."""
    if KNOWN_PRODUCT_ID is None:
        pytest.skip(
            "KNOWN_PRODUCT_ID env var is not set. "
            "Set it to a valid product ID from the catalog to run this test."
        )


def _ensure_stock(quantity: int = 50) -> None:
    """Top up inventory for KNOWN_PRODUCT_ID so tests don't fail on stock=0."""
    response = httpx.put(
        f"{INVENTORY_DIRECT_URL}/inventory/{KNOWN_PRODUCT_ID}/adjust",
        json={"quantityDelta": quantity},
    )
    assert response.status_code == 200, (
        f"Failed to restock product {KNOWN_PRODUCT_ID}: {response.status_code} {response.text}"
    )


def poll_order_status(
    gateway_url: str, order_id: int, token: str, timeout: int = SAGA_TIMEOUT_SECONDS
) -> str:
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


def _seed_cart_and_create_order(gateway_url: str, token: str) -> tuple[int, str]:
    """
    Clear the cart, add KNOWN_PRODUCT_ID, then POST /orders.
    Returns (orderId, correlationId).
    Asserts each step succeeds.
    """
    _ensure_stock()
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
    body = order_resp.json()
    order_id = body.get("id")
    correlation_id = body.get("correlationId")
    assert order_id is not None, f"'id' missing from order creation response: {body}"
    assert correlation_id is not None, f"'correlationId' missing from order creation response: {body}"
    return int(order_id), correlation_id


def _clear_mailhog_inbox() -> None:
    """Delete all messages from MailHog's in-memory store."""
    httpx.delete(f"{MAILHOG_URL}/api/v1/messages")


def _get_messages_for_recipient(email: str) -> list[dict]:
    """
    Query MailHog for all messages sent to a specific email address.
    Returns a list of message dicts (may be empty).
    """
    response = httpx.get(
        f"{MAILHOG_URL}/api/v2/search",
        params={"kind": "to", "query": email},
    )
    assert response.status_code == 200, (
        f"MailHog search returned {response.status_code}: {response.text}"
    )
    return response.json().get("items", [])


def poll_for_email(
    recipient_email: str,
    subject_contains: str,
    timeout: int = EMAIL_TIMEOUT_SECONDS,
) -> dict:
    """
    Poll MailHog until an email arrives for recipient_email whose subject contains
    subject_contains, or the timeout expires.

    Returns the matching message dict.
    Raises TimeoutError if no matching email arrives within the timeout.
    Polls every 1 second.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = _get_messages_for_recipient(recipient_email)
        for msg in messages:
            subject = msg.get("Content", {}).get("Headers", {}).get("Subject", [""])[0]
            if subject_contains.lower() in subject.lower():
                return msg
        time.sleep(1)
    raise TimeoutError(
        f"No email with subject containing '{subject_contains}' arrived for "
        f"{recipient_email!r} within {timeout}s."
    )


def _get_message_body(msg: dict) -> str:
    """Extract the plain-text body from a MailHog message dict."""
    return msg.get("Content", {}).get("Body", "")


# ===========================================================================
# MailHog connectivity
# ===========================================================================

class TestMailHogConnectivity:
    """
    Smoke tests to confirm MailHog is reachable before running email assertions.
    These are fast and do not require the full stack — only MailHog running.
    """

    def test_mailhog_api_is_reachable(self) -> None:
        """
        GET /api/v2/messages must return 200. If this fails, all notification tests
        will also fail — this test surfaces the root cause clearly.
        """
        response = httpx.get(f"{MAILHOG_URL}/api/v2/messages")

        assert response.status_code == 200, (
            f"MailHog API not reachable at {MAILHOG_URL} — "
            f"got {response.status_code}: {response.text}"
        )

    def test_mailhog_messages_response_has_expected_shape(self) -> None:
        """
        The /api/v2/messages response must be a JSON object containing
        'total', 'count', and 'items' keys — the standard MailHog envelope.
        """
        response = httpx.get(f"{MAILHOG_URL}/api/v2/messages")

        assert response.status_code == 200
        body = response.json()
        for key in ("total", "count", "items"):
            assert key in body, (
                f"Expected MailHog response to contain '{key}', got keys: {list(body.keys())}"
            )

    def test_mailhog_inbox_can_be_cleared(self) -> None:
        """
        DELETE /api/v1/messages must return 200. Inbox clearing is used before
        every end-to-end email test to prevent cross-test contamination.
        Note: MailHog delete lives on v1, not v2 — v2 is read-only.
        """
        response = httpx.delete(f"{MAILHOG_URL}/api/v1/messages")

        assert response.status_code == 200, (
            f"MailHog DELETE /api/v1/messages returned {response.status_code}: {response.text}"
        )

    def test_cleared_inbox_has_zero_items(self) -> None:
        """
        After clearing, GET /api/v2/messages must return count=0 and an empty
        items list. This validates the clear operation's effect, not just its HTTP status.
        """
        httpx.delete(f"{MAILHOG_URL}/api/v1/messages")
        response = httpx.get(f"{MAILHOG_URL}/api/v2/messages")

        assert response.status_code == 200
        body = response.json()
        assert body.get("count") == 0, (
            f"Expected 0 messages after clearing inbox, got count={body.get('count')}"
        )
        assert body.get("items") == [], (
            f"Expected empty items list after clearing inbox, got: {body.get('items')}"
        )


# ===========================================================================
# Happy path: ORDER_CONFIRMED email
# ===========================================================================

class TestOrderConfirmedEmail:
    """
    Validates that an ORDER_CONFIRMED email is sent when the Saga happy path completes.

    Setup: clear inbox -> place order -> wait for CONFIRMED -> poll MailHog.
    Each test is independent: inbox is cleared at the start.
    """

    def test_confirmation_email_arrives_after_saga_confirms(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        After an order reaches CONFIRMED status, at least one email must arrive in
        MailHog for the registered user's email address within EMAIL_TIMEOUT_SECONDS.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]

        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        msg = poll_for_email(recipient, "confirmed")

        assert msg is not None, (
            f"Expected a confirmation email for {recipient!r} after order {order_id} "
            f"confirmed, but none arrived within {EMAIL_TIMEOUT_SECONDS}s."
        )

    def test_confirmation_email_subject_contains_order_id(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        The subject line of the confirmation email must contain the order ID so the
        user can identify which order was confirmed at a glance.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]

        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        msg = poll_for_email(recipient, "confirmed")
        subject = msg.get("Content", {}).get("Headers", {}).get("Subject", [""])[0]

        assert str(order_id) in subject, (
            f"Expected order ID {order_id} in email subject, got: {subject!r}"
        )

    def test_confirmation_email_is_sent_to_registered_user_email(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        The To: address on the confirmation email must match the registered user's
        email address. An email sent to the wrong address is a critical delivery failure.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]

        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        msg = poll_for_email(recipient, "confirmed")
        to_headers = msg.get("Content", {}).get("Headers", {}).get("To", [])
        to_address = to_headers[0] if to_headers else ""

        assert recipient.lower() in to_address.lower(), (
            f"Expected email To: to contain {recipient!r}, got: {to_address!r}"
        )

    def test_confirmation_email_body_is_not_empty(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        The email body must not be empty. An empty body means the EmailService
        built an empty string or the mail was constructed incorrectly.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]

        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        msg = poll_for_email(recipient, "confirmed")
        body = _get_message_body(msg)

        assert body.strip(), (
            "Expected non-empty email body for confirmation email, got empty string."
        )

    def test_no_failure_email_sent_on_happy_path(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        A successful order must NOT trigger a failure email. After the Saga confirms,
        searching MailHog for a 'failed' subject for the recipient must return nothing.
        This catches double-firing bugs where both email types are sent.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]

        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        # Allow time for any erroneous failure email to arrive before asserting absence.
        time.sleep(3)
        messages = _get_messages_for_recipient(recipient)
        failure_emails = [
            m for m in messages
            if "failed" in m.get("Content", {}).get("Headers", {}).get("Subject", [""])[0].lower()
        ]

        assert len(failure_emails) == 0, (
            f"Expected no failure email on happy path, but found {len(failure_emails)}: "
            f"{[m.get('Content', {}).get('Headers', {}).get('Subject') for m in failure_emails]}"
        )


# ===========================================================================
# Compensation path: ORDER_FAILED email
# ===========================================================================

class TestOrderFailedEmail:
    """
    Validates that an ORDER_FAILED email is sent when the Saga compensation path runs.

    Setup: clear inbox -> register simulate-failure -> place order -> wait for FAILED
    -> poll MailHog for failure email.
    """

    def test_failure_email_arrives_after_saga_fails(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        After an order reaches FAILED status due to simulate-failure, at least one
        email with a failure-related subject must arrive for the user's email address.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]
        user_id = _get_user_id_from_token(token)

        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/next-for-user/{user_id}"
        )
        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "FAILED", (
            f"Order {order_id} did not reach FAILED: {final_status}"
        )

        msg = poll_for_email(recipient, "failed")

        assert msg is not None, (
            f"Expected a failure email for {recipient!r} after order {order_id} failed, "
            f"but none arrived within {EMAIL_TIMEOUT_SECONDS}s."
        )

    def test_failure_email_subject_contains_order_id(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        The subject of the failure email must contain the order ID so the user knows
        which specific order failed.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]
        user_id = _get_user_id_from_token(token)

        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/next-for-user/{user_id}"
        )
        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "FAILED", (
            f"Order {order_id} did not reach FAILED: {final_status}"
        )

        msg = poll_for_email(recipient, "failed")
        subject = msg.get("Content", {}).get("Headers", {}).get("Subject", [""])[0]

        assert str(order_id) in subject, (
            f"Expected order ID {order_id} in failure email subject, got: {subject!r}"
        )

    def test_failure_email_is_sent_to_registered_user_email(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        The To: address on the failure email must match the registered user's email.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]
        user_id = _get_user_id_from_token(token)

        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/next-for-user/{user_id}"
        )
        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "FAILED", (
            f"Order {order_id} did not reach FAILED: {final_status}"
        )

        msg = poll_for_email(recipient, "failed")
        to_headers = msg.get("Content", {}).get("Headers", {}).get("To", [])
        to_address = to_headers[0] if to_headers else ""

        assert recipient.lower() in to_address.lower(), (
            f"Expected failure email To: to contain {recipient!r}, got: {to_address!r}"
        )

    def test_failure_email_body_is_not_empty(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        The failure email body must not be empty.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]
        user_id = _get_user_id_from_token(token)

        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/next-for-user/{user_id}"
        )
        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "FAILED", (
            f"Order {order_id} did not reach FAILED: {final_status}"
        )

        msg = poll_for_email(recipient, "failed")
        body = _get_message_body(msg)

        assert body.strip(), (
            "Expected non-empty email body for failure email, got empty string."
        )

    def test_no_confirmation_email_sent_on_failure_path(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        A failed order must NOT trigger a confirmation email. After the Saga fails,
        MailHog must not contain any email with 'confirmed' in the subject for
        this recipient. This catches bugs where both emails fire simultaneously.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]
        user_id = _get_user_id_from_token(token)

        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/next-for-user/{user_id}"
        )
        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "FAILED", (
            f"Order {order_id} did not reach FAILED: {final_status}"
        )

        # Allow time for any erroneous confirmation email to arrive.
        time.sleep(3)
        messages = _get_messages_for_recipient(recipient)
        confirmation_emails = [
            m for m in messages
            if "confirmed" in m.get("Content", {}).get("Headers", {}).get("Subject", [""])[0].lower()
        ]

        assert len(confirmation_emails) == 0, (
            f"Expected no confirmation email on failure path, but found {len(confirmation_emails)}: "
            f"{[m.get('Content', {}).get('Headers', {}).get('Subject') for m in confirmation_emails]}"
        )


# ===========================================================================
# Email isolation: one email per event
# ===========================================================================

class TestEmailIsolation:
    """
    Validates that exactly one email is sent per order event — not zero, not two.
    Prevents double-firing (consumer invoked twice) and missed-firing bugs.
    """

    def test_exactly_one_confirmation_email_per_confirmed_order(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        One ORDER_CONFIRMED event must produce exactly one confirmation email.
        Multiple emails for the same order would indicate the Kafka consumer was
        triggered more than once (e.g., missing idempotency check or re-delivery bug).
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]

        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "CONFIRMED", (
            f"Order {order_id} did not reach CONFIRMED: {final_status}"
        )

        # Wait for email delivery then add a small buffer for any duplicates.
        poll_for_email(recipient, "confirmed")
        time.sleep(3)

        messages = _get_messages_for_recipient(recipient)
        confirmation_emails = [
            m for m in messages
            if "confirmed" in m.get("Content", {}).get("Headers", {}).get("Subject", [""])[0].lower()
               and str(order_id) in m.get("Content", {}).get("Headers", {}).get("Subject", [""])[0]
        ]

        assert len(confirmation_emails) == 1, (
            f"Expected exactly 1 confirmation email for order {order_id}, "
            f"got {len(confirmation_emails)}. Possible double-fire or consumer re-delivery issue."
        )

    def test_exactly_one_failure_email_per_failed_order(
        self, gateway_url: str, auth_tokens: dict, registered_user: dict
    ) -> None:
        """
        One ORDER_COMPENSATION event must produce exactly one failure email.
        """
        _require_known_product()
        _clear_mailhog_inbox()
        token = auth_tokens["access_token"]
        recipient = registered_user["email"]
        user_id = _get_user_id_from_token(token)

        httpx.post(
            f"{PAYMENT_DIRECT_URL}/internal/payments/simulate-failure/next-for-user/{user_id}"
        )
        order_id, _ = _seed_cart_and_create_order(gateway_url, token)
        final_status = poll_order_status(gateway_url, order_id, token)
        assert final_status == "FAILED", (
            f"Order {order_id} did not reach FAILED: {final_status}"
        )

        poll_for_email(recipient, "failed")
        time.sleep(3)

        messages = _get_messages_for_recipient(recipient)
        failure_emails = [
            m for m in messages
            if "failed" in m.get("Content", {}).get("Headers", {}).get("Subject", [""])[0].lower()
               and str(order_id) in m.get("Content", {}).get("Headers", {}).get("Subject", [""])[0]
        ]

        assert len(failure_emails) == 1, (
            f"Expected exactly 1 failure email for order {order_id}, "
            f"got {len(failure_emails)}. Possible double-fire or consumer re-delivery issue."
        )
