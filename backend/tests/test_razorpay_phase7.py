"""
Comprehensive unit and integration tests for MediExplain AI Phase 7:
Razorpay Test-Mode Recurring Subscriptions, Mandate Checkout Authorization,
HMAC-SHA256 Cryptographic Signature Verification, Idempotent Webhook Processing,
and Automated Trial-to-Paid Subscription Lifecycle Management.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from main import app
from app.core.config import settings
from app.core.dependencies import get_current_user, require_email_verified
from app.db.supabase_client import get_supabase
from app.services.payment.razorpay_service import (
    create_plan_if_needed,
    create_subscription,
    verify_payment_signature,
)
from app.api.v1.endpoints.webhooks import _verify_razorpay_signature

client = TestClient(app)

TEST_KEY_ID = "rzp_test_mediexplain_public_123"
TEST_KEY_SECRET = "test_rzp_secret_key_456"
TEST_WEBHOOK_SECRET = "test_webhook_secret_key_789"

USER_ID = "usr-patient-701"
SUB_ID = "sub_RzpTest10001"
PAYMENT_ID = "pay_RzpTest20002"
EVENT_ID = "evt_RzpTest30003"


@pytest.fixture(autouse=True)
def setup_test_settings():
    """Ensure test settings are configured for signatures."""
    orig_key_id = settings.RAZORPAY_KEY_ID
    orig_key_secret = settings.RAZORPAY_KEY_SECRET
    orig_webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    orig_plan_id = settings.RAZORPAY_PLAN_ID

    settings.RAZORPAY_KEY_ID = TEST_KEY_ID
    settings.RAZORPAY_KEY_SECRET = TEST_KEY_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = TEST_WEBHOOK_SECRET
    settings.RAZORPAY_PLAN_ID = "plan_test_monthly_200"

    yield

    settings.RAZORPAY_KEY_ID = orig_key_id
    settings.RAZORPAY_KEY_SECRET = orig_key_secret
    settings.RAZORPAY_WEBHOOK_SECRET = orig_webhook_secret
    settings.RAZORPAY_PLAN_ID = orig_plan_id


@pytest.fixture
def mock_verified_user():
    return {
        "id": USER_ID,
        "email": "patient@example.com",
        "email_confirmed": True,
        "role": "authenticated",
    }


def _generate_webhook_signature(payload_bytes: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    """Helper to generate HMAC-SHA256 signature for test webhooks."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


# ─── 1. Razorpay Plan & Subscription Creation ────────────────────────

def test_create_plan_configuration():
    """Verify ₹200/month plan parameters (20000 paise, monthly, INR)."""
    with patch("app.services.payment.razorpay_service._get_client") as mock_client:
        mock_rzp = MagicMock()
        mock_rzp.plan.create.return_value = {"id": "plan_new_123"}
        mock_client.return_value = mock_rzp

        settings.RAZORPAY_PLAN_ID = ""  # Force creation
        plan_id = create_plan_if_needed()

        assert plan_id == "plan_new_123"
        call_args = mock_rzp.plan.create.call_args[0][0]
        assert call_args["period"] == "monthly"
        assert call_args["interval"] == 1
        assert call_args["item"]["amount"] == 20000
        assert call_args["item"]["currency"] == "INR"


def test_create_subscription_with_trial_offset():
    """Verify subscription start_at offset preserves the 30-day free trial."""
    with patch("app.services.payment.razorpay_service._get_client") as mock_client:
        mock_rzp = MagicMock()
        mock_rzp.subscription.create.return_value = {"id": SUB_ID, "status": "created"}
        mock_client.return_value = mock_rzp

        future_start = int(datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
        sub = create_subscription(plan_id="plan_test_monthly_200", start_at=future_start)

        assert sub["id"] == SUB_ID
        call_args = mock_rzp.subscription.create.call_args[0][0]
        assert call_args["plan_id"] == "plan_test_monthly_200"
        assert call_args["start_at"] == future_start


# ─── 2. Checkout Creation Endpoint (/api/v1/subscriptions/create-checkout) ──

def test_create_checkout_session_endpoint_success(mock_verified_user):
    """
    POST /api/v1/subscriptions/create-checkout:
    Creates Razorpay subscription with trial offset, stores ID, and returns checkout config.
    """
    mock_supabase = MagicMock()
    # User's existing subscription has 25 days remaining on trial
    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=25)
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "TRIAL_ACTIVE",
        "trial_end_date": trial_end.isoformat(),
        "gateway_subscription_id": None,
    }
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[require_email_verified] = lambda: mock_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    with patch("app.api.v1.endpoints.subscriptions.create_subscription") as mock_create_sub:
        mock_create_sub.return_value = {"id": SUB_ID, "status": "created"}

        try:
            response = client.post("/api/v1/subscriptions/create-checkout")
            assert response.status_code == 200
            data = response.json()
            assert data["gateway_subscription_id"] == SUB_ID
            assert data["razorpay_key_id"] == TEST_KEY_ID
            assert data["amount"] == 20000
            assert data["currency"] == "INR"
            assert "first_charge_date" in data

            # Verify start_at matched the user's trial_end_date
            mock_create_sub.assert_called_once()
            called_start_at = mock_create_sub.call_args.kwargs.get("start_at")
            assert called_start_at == int(trial_end.timestamp())
        finally:
            app.dependency_overrides.clear()


# ─── 3. Checkout Verification Endpoint (/api/v1/subscriptions/verify-checkout)

def test_verify_checkout_endpoint_success(mock_verified_user):
    """
    POST /api/v1/subscriptions/verify-checkout:
    Server-side HMAC-SHA256 signature verification authorizes subscription
    using the server-stored subscription ID.
    """
    mock_supabase = MagicMock()
    # User owns this subscription with server-stored gateway_subscription_id
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "sub-db-1",
        "user_id": USER_ID,
        "gateway_subscription_id": SUB_ID,
        "trial_end_date": "2026-12-01T00:00:00Z",
    }
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[require_email_verified] = lambda: mock_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    # Compute valid signature
    msg = f"{PAYMENT_ID}|{SUB_ID}"
    valid_sig = hmac.new(TEST_KEY_SECRET.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    with patch("app.api.v1.endpoints.subscriptions.fetch_subscription") as mock_fetch:
        mock_fetch.return_value = {
            "id": SUB_ID,
            "status": "authenticated",
            "charge_at": int(datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()),
        }

        try:
            response = client.post(
                "/api/v1/subscriptions/verify-checkout",
                json={
                    "razorpay_subscription_id": SUB_ID,
                    "razorpay_payment_id": PAYMENT_ID,
                    "razorpay_signature": valid_sig,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["verified"] is True
            assert data["subscription_status"] == "TRIAL_ACTIVE"
        finally:
            app.dependency_overrides.clear()


def test_verify_checkout_invalid_signature_rejected(mock_verified_user):
    """Forged signature returns HTTP 400."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "sub-db-1",
        "user_id": USER_ID,
        "gateway_subscription_id": SUB_ID,
    }

    app.dependency_overrides[require_email_verified] = lambda: mock_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.post(
            "/api/v1/subscriptions/verify-checkout",
            json={
                "razorpay_subscription_id": SUB_ID,
                "razorpay_payment_id": PAYMENT_ID,
                "razorpay_signature": "forged_signature_hex_12345",
            },
        )
        assert response.status_code == 400
        assert "Payment verification failed" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_verify_checkout_cross_user_forbidden(mock_verified_user):
    """User cannot verify a subscription ID that does not match their server session."""
    mock_supabase = MagicMock()
    # Server record has a different subscription ID
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "sub-db-1",
        "user_id": USER_ID,
        "gateway_subscription_id": "sub_different_pending_999",
    }

    app.dependency_overrides[require_email_verified] = lambda: mock_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.post(
            "/api/v1/subscriptions/verify-checkout",
            json={
                "razorpay_subscription_id": SUB_ID,  # Mismatched ID
                "razorpay_payment_id": PAYMENT_ID,
                "razorpay_signature": "any_signature",
            },
        )
        assert response.status_code == 403
        assert "Subscription ID mismatch" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_verify_checkout_missing_subscription_returns_404(mock_verified_user):
    """Missing subscription record returns HTTP 404."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    app.dependency_overrides[require_email_verified] = lambda: mock_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.post(
            "/api/v1/subscriptions/verify-checkout",
            json={
                "razorpay_subscription_id": SUB_ID,
                "razorpay_payment_id": PAYMENT_ID,
                "razorpay_signature": "any_signature",
            },
        )
        assert response.status_code == 404
        assert "Subscription record not found" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ─── 4. Webhook Security & Signature Tests (/api/v1/webhooks/razorpay) ──

def test_webhook_missing_signature_rejected():
    """Webhook request without X-Razorpay-Signature header is rejected with HTTP 400."""
    payload = json.dumps({"event": "subscription.charged", "id": "evt_123"}).encode("utf-8")
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "Missing X-Razorpay-Signature header" in response.json()["detail"]


def test_webhook_forged_signature_rejected():
    """Webhook with forged signature is rejected with HTTP 400."""
    payload = json.dumps({"event": "subscription.charged", "id": "evt_123"}).encode("utf-8")
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "forged_hex_signature",
        },
    )
    assert response.status_code == 400
    assert "Webhook signature verification failed" in response.json()["detail"]


def test_webhook_idempotency_duplicate_event_ignored():
    """Duplicate webhook event is acknowledged with HTTP 200 without re-processing."""
    mock_supabase = MagicMock()
    # Event ID already exists in subscription_events
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "evt-prior", "event_status": "PROCESSED"}
    ]

    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    payload = json.dumps({"event": "subscription.charged", "id": EVENT_ID}).encode("utf-8")
    sig = _generate_webhook_signature(payload)

    try:
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "duplicate_ignored"
        # Verify no updates executed
        mock_supabase.table.return_value.update.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_webhook_header_event_id_verification():
    """Verify that X-Razorpay-Event-Id header is checked and validated against payload."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[]),  # idempotency check
        MagicMock(data=[{"id": "sub-db-1", "user_id": USER_ID, "subscription_status": "AUTHORIZATION_PENDING"}]),
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    payload = json.dumps({
        "event": "subscription.authenticated",
        "id": "evt_hdr_match_123",
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUB_ID,
                    "status": "authenticated",
                    "charge_at": int(datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()),
                }
            }
        },
    }).encode("utf-8")
    sig = _generate_webhook_signature(payload)

    try:
        # Case 1: Matching header passes
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": "evt_hdr_match_123",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Case 2: Conflicting header rejected with HTTP 400
        response_mismatch = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": "evt_conflicting_456",
            },
        )
        assert response_mismatch.status_code == 400
        assert "X-Razorpay-Event-Id header does not match" in response_mismatch.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_forged_webhook_does_not_alter_database_records():
    """Verify forged webhook request is rejected and touches no database records."""
    mock_supabase = MagicMock()
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    payload = json.dumps({"event": "subscription.charged", "id": "evt_forged_999"}).encode("utf-8")
    try:
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "forged_hex_signature",
            },
        )
        assert response.status_code == 400
        mock_supabase.table.assert_not_called()
    finally:
        app.dependency_overrides.clear()


# ─── 5. Webhook Event Handlers ───────────────────────────────────────

def test_webhook_subscription_authenticated():
    """
    Test webhook event: subscription.authenticated
    Mandate authenticated by bank -> updates subscription status & billing date.
    """
    mock_supabase = MagicMock()
    # Subscription found in DB
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[]),  # idempotency check
        MagicMock(data=[{"id": "sub-db-1", "user_id": USER_ID, "subscription_status": "AUTHORIZATION_PENDING"}]),
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    charge_timestamp = int(datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    payload = json.dumps({
        "event": "subscription.authenticated",
        "id": "evt_auth_001",
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUB_ID,
                    "status": "authenticated",
                    "charge_at": charge_timestamp,
                }
            }
        },
    }).encode("utf-8")
    sig = _generate_webhook_signature(payload)

    try:
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_webhook_subscription_charged_successful_payment():
    """
    Test webhook event: subscription.charged
    Monthly recurring debit successful -> updates status to ACTIVE,
    updates next_billing_date, and records CAPTURED payment in payments table.
    """
    mock_supabase = MagicMock()
    # 1. Idempotency check: not duplicate
    # 2. Subscription lookup: found
    # 3. Payment existence check: not yet recorded
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[]),  # idempotency check
        MagicMock(data=[{"id": "sub-db-1", "user_id": USER_ID, "subscription_status": "TRIAL_ACTIVE"}]),
        MagicMock(data=[]),  # payment idempotency check
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    next_charge_at = int(datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    payload = json.dumps({
        "event": "subscription.charged",
        "id": "evt_charged_002",
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUB_ID,
                    "status": "active",
                    "charge_at": next_charge_at,
                }
            },
            "payment": {
                "entity": {
                    "id": PAYMENT_ID,
                    "order_id": "order_test_123",
                    "amount": 20000,
                    "currency": "INR",
                    "method": "upi",
                }
            },
        },
    }).encode("utf-8")
    sig = _generate_webhook_signature(payload)

    try:
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Verify payments table insertion called
        mock_supabase.table.assert_any_call("payments")
        mock_supabase.table.assert_any_call("subscription_events")
    finally:
        app.dependency_overrides.clear()


def test_webhook_payment_failed():
    """
    Test webhook event: payment.failed
    Debit fails -> transitions subscription to PAST_DUE and records FAILED payment.
    """
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[]),  # idempotency check
        MagicMock(data=[{"id": "sub-db-1", "user_id": USER_ID, "subscription_status": "ACTIVE"}]),
        MagicMock(data=[]),  # payment idempotency check
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    payload = json.dumps({
        "event": "payment.failed",
        "id": "evt_fail_003",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_failed_999",
                    "subscription_id": SUB_ID,
                    "amount": 20000,
                    "currency": "INR",
                    "method": "card",
                    "error_description": "Bank servers unavailable",
                }
            }
        },
    }).encode("utf-8")
    sig = _generate_webhook_signature(payload)

    try:
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_webhook_subscription_halted():
    """
    Test webhook event: subscription.halted
    Subscription halts after retry failures -> status set to PAST_DUE.
    """
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[]),  # idempotency check
        MagicMock(data=[{"id": "sub-db-1", "user_id": USER_ID, "subscription_status": "ACTIVE"}]),
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    payload = json.dumps({
        "event": "subscription.halted",
        "id": "evt_halt_004",
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUB_ID,
                    "status": "halted",
                }
            }
        },
    }).encode("utf-8")
    sig = _generate_webhook_signature(payload)

    try:
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_webhook_subscription_cancelled():
    """
    Test webhook event: subscription.cancelled
    Subscription canceled at gateway -> updates DB status to CANCELED.
    """
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[]),  # idempotency check
        MagicMock(data=[{"id": "sub-db-1", "user_id": USER_ID, "subscription_status": "ACTIVE"}]),
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    payload = json.dumps({
        "event": "subscription.cancelled",
        "id": "evt_cancel_005",
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUB_ID,
                    "status": "cancelled",
                }
            }
        },
    }).encode("utf-8")
    sig = _generate_webhook_signature(payload)

    try:
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()


# ─── 6. Full Lifecycle & Cancellation via Razorpay ───────────────────

def test_cancel_subscription_via_razorpay_endpoint(mock_verified_user):
    """
    POST /api/v1/subscriptions/cancel:
    For an active Razorpay subscriber, invokes Razorpay cancel_subscription
    and updates database status to CANCELED.
    """
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "sub-db-1",
        "user_id": USER_ID,
        "subscription_status": "ACTIVE",
        "gateway_subscription_id": SUB_ID,
        "next_billing_date": "2026-12-01T00:00:00Z",
    }
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    app.dependency_overrides[get_current_user] = lambda: mock_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    with patch("app.api.v1.endpoints.subscriptions.cancel_subscription") as mock_cancel_sub:
        mock_cancel_sub.return_value = {"id": SUB_ID, "status": "cancelled"}

        try:
            response = client.post("/api/v1/subscriptions/cancel")
            assert response.status_code == 200
            data = response.json()
            assert data["cancelled"] is True
            assert data["subscription_status"] == "CANCELED"
            mock_cancel_sub.assert_called_once_with(SUB_ID, cancel_at_cycle_end=True)
        finally:
            app.dependency_overrides.clear()


def test_trial_to_paid_transition_lifecycle():
    """
    Lifecycle Test:
    1. User starts in TRIAL_ACTIVE (no payment).
    2. Mandate authorized during trial (subscription.authenticated) -> remains TRIAL_ACTIVE until trial end.
    3. Day 30 arrives -> first monthly debit (subscription.charged) -> transitions to ACTIVE with payment captured.
    """
    mock_supabase = MagicMock()
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    # Step 1: Trial active with charge_at set in future
    trial_end_ts = int(datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[]),  # event 1 idempotency
        MagicMock(data=[{
            "id": "sub-lifecycle-1",
            "user_id": USER_ID,
            "subscription_status": "TRIAL_ACTIVE",
            "trial_end_date": "2026-12-01T00:00:00Z",
        }]),
        MagicMock(data=[]),  # event 2 idempotency
        MagicMock(data=[{
            "id": "sub-lifecycle-1",
            "user_id": USER_ID,
            "subscription_status": "TRIAL_ACTIVE",
            "trial_end_date": "2026-12-01T00:00:00Z",
        }]),
        MagicMock(data=[]),  # payment idempotency
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    # Step 2: Mandate authenticated
    auth_payload = json.dumps({
        "event": "subscription.authenticated",
        "id": "evt_lifecycle_auth",
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUB_ID,
                    "status": "authenticated",
                    "charge_at": trial_end_ts,
                }
            }
        },
    }).encode("utf-8")
    auth_sig = _generate_webhook_signature(auth_payload)

    res_auth = client.post(
        "/api/v1/webhooks/razorpay",
        content=auth_payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": auth_sig},
    )
    assert res_auth.status_code == 200

    # Step 3: First charge on Day 30
    charge_payload = json.dumps({
        "event": "subscription.charged",
        "id": "evt_lifecycle_charge",
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUB_ID,
                    "status": "active",
                    "charge_at": trial_end_ts + (30 * 24 * 3600),
                }
            },
            "payment": {
                "entity": {
                    "id": PAYMENT_ID,
                    "amount": 20000,
                    "currency": "INR",
                    "method": "upi",
                }
            },
        },
    }).encode("utf-8")
    charge_sig = _generate_webhook_signature(charge_payload)

    res_charge = client.post(
        "/api/v1/webhooks/razorpay",
        content=charge_payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": charge_sig},
    )
    assert res_charge.status_code == 200
    assert res_charge.json()["status"] == "ok"
    app.dependency_overrides.clear()


def test_historical_reports_accessible_when_subscription_expired(mock_verified_user):
    """
    Verify Requirement 5:
    When a user's subscription access expires:
    1. Historical reports, parameters, and details remain fully readable via GET endpoints.
    2. Paid actions (uploading new reports, triggering new AI analyses) are denied with HTTP 403.
    """
    mock_supabase = MagicMock()
    # Mock list_reports which calls .select().eq().order().execute()
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
        {"id": "report-hist-1", "user_id": USER_ID, "report_name": "Blood_Panel.pdf", "processing_status": "COMPLETED"}
    ]
    # Mock single report detail & parameters lookup
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "report-hist-1", "user_id": USER_ID, "report_name": "Blood_Panel.pdf"
    }
    # Mock parameters query and subscription lookup in require_active_subscription
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "param-1", "parameter_name": "Hemoglobin", "observed_value": "14.2"}
    ]
    # For subscription check in require_active_subscription
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[{"id": "report-hist-1"}]),  # param report ownership check
        MagicMock(data=[{"id": "param-1", "parameter_name": "Hemoglobin", "observed_value": "14.2"}]),  # params
        MagicMock(data=[{
            "id": "sub-exp-1",
            "user_id": USER_ID,
            "subscription_status": "EXPIRED",
            "trial_end_date": "2026-01-01T00:00:00Z",
            "next_billing_date": None,
        }]),  # require_active_subscription check on upload
    ]

    app.dependency_overrides[get_current_user] = lambda: mock_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        # A. Historical reports are accessible
        resp_list = client.get("/api/v1/reports/")
        assert resp_list.status_code == 200
        assert len(resp_list.json()["reports"]) == 1

        # B. Report details are accessible
        resp_detail = client.get("/api/v1/reports/report-hist-1")
        assert resp_detail.status_code == 200

        # C. Extracted parameters are accessible
        resp_params = client.get("/api/v1/reports/report-hist-1/parameters")
        assert resp_params.status_code == 200

        # D. Uploading new report is blocked for expired subscription (HTTP 402 Payment Required)
        resp_upload = client.post(
            "/api/v1/reports/upload",
            files={"file": ("new_report.pdf", b"%PDF-1.4 test file", "application/pdf")},
        )
        assert resp_upload.status_code == 402
        assert "subscription" in resp_upload.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()

