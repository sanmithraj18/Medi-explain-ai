"""
Comprehensive unit and integration tests for MediExplain AI Phase 6:
30-Day Free Trial System, Subscription Status Management,
Server-Side Access Control, Duplicate Trial Abuse Prevention,
and Subscription Cancellation Workflows.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from app.core.dependencies import get_current_user, require_active_subscription
from app.db.supabase_client import get_supabase
from app.services.subscription.trial_service import (
    normalize_email,
    calculate_trial_period,
    get_trial_days_remaining,
    evaluate_subscription_access,
    check_duplicate_trial_abuse,
    CANONICAL_STATUS_MAP,
)

client = TestClient(app)

USER_ID = "usr-trial-101"
DUPLICATE_USER_ID = "usr-duplicate-909"
OTHER_USER_ID = "usr-existing-002"


@pytest.fixture
def mock_user():
    return {
        "id": USER_ID,
        "email": "sarah.patient@example.com",
        "email_confirmed": True,
        "role": "authenticated",
    }


# ─── 1. Trial Calculation & Duration Tests ───────────────────────────

def test_trial_period_calculation_30_days():
    """Verify trial duration is strictly 30 calendar days in UTC."""
    fixed_start = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    start, end = calculate_trial_period(fixed_start, days=30)

    assert start == fixed_start
    assert end == datetime(2026, 12, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert (end - start).days == 30
    assert (end - start).total_seconds() == 30 * 86400


def test_trial_days_remaining_countdown():
    """Verify trial countdown calculations across various time deltas."""
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)

    # 30 days in future
    end_30d = now + timedelta(days=30)
    assert get_trial_days_remaining(end_30d, now) == 30

    # 15.5 days in future -> 15 full days
    end_15d = now + timedelta(days=15, hours=12)
    assert get_trial_days_remaining(end_15d, now) == 15

    # 10 hours in future -> 0 full days (last day of trial)
    end_hours = now + timedelta(hours=10)
    assert get_trial_days_remaining(end_hours, now) == 0

    # Exactly now
    assert get_trial_days_remaining(now, now) == 0

    # Expired in past
    end_past = now - timedelta(days=1)
    assert get_trial_days_remaining(end_past, now) == 0

    # None / empty string
    assert get_trial_days_remaining(None, now) == 0


def test_timezone_and_date_boundary_cases():
    """Test date parsing handles Z suffix, numeric offsets, and leap/month rollovers."""
    now = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    # Feb rollover in non-leap year (2026 has 28 days in Feb)
    _, end = calculate_trial_period(now, days=30)
    assert end == datetime(2026, 3, 3, 0, 0, 0, tzinfo=timezone.utc)

    # Offset timestamp format '+05:30'
    offset_ts = "2026-11-10T12:00:00+05:30"
    days = get_trial_days_remaining(offset_ts, current_time=datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc))
    assert days > 0


# ─── 2. Email Normalization & Duplicate Abuse Prevention ──────────────

def test_email_normalization_abuse_prevention():
    """
    Verify email normalization:
    - Gmail / Googlemail: dot removal, plus-tag removal, domain unified to gmail.com.
    - Non-Gmail (Yahoo, Outlook, unknown): address preserved exactly (lowercase and trimmed).
    """
    # Gmail: dots and plus tags stripped
    assert normalize_email("john.doe@gmail.com") == "johndoe@gmail.com"
    assert normalize_email("j.o.h.n.d.o.e@gmail.com") == "johndoe@gmail.com"
    assert normalize_email("johndoe+trial2@gmail.com") == "johndoe@gmail.com"
    assert normalize_email("john.doe+promo@gmail.com") == "johndoe@gmail.com"

    # Googlemail: mapped to gmail with dots and plus tags stripped
    assert normalize_email("john.doe@googlemail.com") == "johndoe@gmail.com"
    assert normalize_email("john.doe+promo@googlemail.com") == "johndoe@gmail.com"

    # Non-Gmail providers: dots and plus tags are strictly preserved
    assert normalize_email("patient+test@outlook.com") == "patient+test@outlook.com"
    assert normalize_email("user.name+trial@yahoo.com") == "user.name+trial@yahoo.com"
    assert normalize_email("doctor.jones+cardio@icloud.com") == "doctor.jones+cardio@icloud.com"
    assert normalize_email("specialist.smith+tag@hospital.edu") == "specialist.smith+tag@hospital.edu"
    assert normalize_email("researcher.alpha+v1@unknown-lab.org") == "researcher.alpha+v1@unknown-lab.org"

    # Case insensitivity & whitespace trimming
    assert normalize_email("  Patient.User+Tag@GMAIL.COM  ") == "patientuser@gmail.com"
    assert normalize_email("  Doctor.Who+Lab@YAHOO.COM  ") == "doctor.who+lab@yahoo.com"


def test_duplicate_trial_prevention_check():
    """Verify check_duplicate_trial_abuse detects existing normalized accounts."""
    mock_supabase = MagicMock()

    # Case A: Another user already exists with this normalized email
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {"id": OTHER_USER_ID, "email": "johndoe@gmail.com"}
    ]
    is_abuse = check_duplicate_trial_abuse("john.doe+trial99@gmail.com", USER_ID, mock_supabase)
    assert is_abuse is True

    # Case B: No other user has this normalized email
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
    is_eligible = check_duplicate_trial_abuse("brand.new.user@gmail.com", USER_ID, mock_supabase)
    assert is_eligible is False


# ─── 3. Canonical Subscription Status Mapping ────────────────────────

def test_canonical_status_mapping():
    """Verify all database states resolve to the 5 canonical subscription states."""
    expected = {
        "TRIAL_ACTIVE": "TRIAL_ACTIVE",
        "ACTIVE": "ACTIVE",
        "AUTHENTICATED": "ACTIVE",
        "PAST_DUE": "PAST_DUE",
        "PAYMENT_PENDING": "PAST_DUE",
        "PAYMENT_FAILED": "PAST_DUE",
        "HALTED": "PAST_DUE",
        "CANCELED": "CANCELED",
        "CANCELLED": "CANCELED",
        "EXPIRED": "EXPIRED",
        "TRIAL_EXPIRED": "EXPIRED",
        "COMPLETED": "EXPIRED",
    }
    for raw, canonical in expected.items():
        assert CANONICAL_STATUS_MAP[raw] == canonical


def test_evaluate_subscription_access():
    """Test evaluation logic for active trials, active paid plans, and expired states."""
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Active trial with valid future date
    trial_sub = {
        "subscription_status": "TRIAL_ACTIVE",
        "trial_end_date": (now + timedelta(days=15)).isoformat(),
    }
    can_access, status_val, days_left = evaluate_subscription_access(trial_sub, now)
    assert can_access is True
    assert status_val == "TRIAL_ACTIVE"
    assert days_left == 15

    # 2. Trial whose end date elapsed
    expired_trial_sub = {
        "subscription_status": "TRIAL_ACTIVE",
        "trial_end_date": (now - timedelta(hours=1)).isoformat(),
    }
    can_access, status_val, days_left = evaluate_subscription_access(expired_trial_sub, now)
    assert can_access is False
    assert status_val == "EXPIRED"
    assert days_left == 0

    # 3. Active paid subscriber
    paid_sub = {"subscription_status": "ACTIVE"}
    can_access, status_val, _ = evaluate_subscription_access(paid_sub, now)
    assert can_access is True
    assert status_val == "ACTIVE"

    # 4. Canceled subscription
    canceled_sub = {"subscription_status": "CANCELED"}
    can_access, status_val, _ = evaluate_subscription_access(canceled_sub, now)
    assert can_access is False
    assert status_val == "CANCELED"

    # 5. Past due subscription
    past_due_sub = {"subscription_status": "PAST_DUE"}
    can_access, status_val, _ = evaluate_subscription_access(past_due_sub, now)
    assert can_access is False
    assert status_val == "PAST_DUE"


# ─── 4. Current Subscription API Endpoint (/api/v1/subscriptions/current) ─

def test_get_current_subscription_provisions_trial_for_new_user(mock_user):
    """
    When a new eligible user queries /current and has no subscription record,
    the endpoint automatically provisions a 30-day free trial.
    """
    mock_supabase = MagicMock()
    # 1. First query: no subscription found
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    # 2. Duplicate abuse check: not abuse
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    # 3. Insert new trial subscription record
    now = datetime.now(timezone.utc)
    created_sub = {
        "id": "sub-new-123",
        "user_id": USER_ID,
        "plan_name": "MediExplain AI Premium",
        "amount": 20000,
        "currency": "INR",
        "subscription_status": "TRIAL_ACTIVE",
        "trial_start_date": now.isoformat(),
        "trial_end_date": (now + timedelta(days=30)).isoformat(),
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [created_sub]

    # 4. Payments query
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get("/api/v1/subscriptions/current")
        assert response.status_code == 200
        data = response.json()
        assert data["plan_name"] == "MediExplain AI Premium"
        assert data["subscription_status"] == "TRIAL_ACTIVE"
        assert data["trial_days_remaining"] >= 29
        assert data["is_trial_active"] is True
        assert data["can_access_paid_features"] is True
        assert data["amount_formatted"] == "₹200"
    finally:
        app.dependency_overrides.clear()


def test_get_current_subscription_duplicate_account_gets_expired(mock_user):
    """
    When a user creates a duplicate account with a normalized email already on record,
    they receive an EXPIRED subscription with 0 trial days.
    """
    mock_supabase = MagicMock()
    # 1. No subscription found
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    # 2. Duplicate check: finds existing account!
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {"id": OTHER_USER_ID, "email": "sarahpatient@example.com"}
    ]

    now = datetime.now(timezone.utc)
    expired_sub = {
        "id": "sub-dup-888",
        "user_id": USER_ID,
        "plan_name": "MediExplain AI Premium",
        "amount": 20000,
        "currency": "INR",
        "subscription_status": "EXPIRED",
        "trial_start_date": now.isoformat(),
        "trial_end_date": now.isoformat(),
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [expired_sub]

    # 3. Payments
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get("/api/v1/subscriptions/current")
        assert response.status_code == 200
        data = response.json()
        assert data["subscription_status"] == "EXPIRED"
        assert data["trial_days_remaining"] == 0
        assert data["can_access_paid_features"] is False
    finally:
        app.dependency_overrides.clear()


def test_get_current_subscription_active_subscriber(mock_user):
    """Verify active paid subscriber details and payment history."""
    mock_supabase = MagicMock()
    active_sub = {
        "id": "sub-active-555",
        "user_id": USER_ID,
        "plan_name": "MediExplain AI Premium",
        "amount": 20000,
        "currency": "INR",
        "subscription_status": "ACTIVE",
        "billing_start_date": "2026-10-01T00:00:00Z",
        "next_billing_date": "2026-11-01T00:00:00Z",
        "gateway_subscription_id": "sub_Rzp12345678",
    }
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [active_sub]

    payments = [
        {
            "id": "pay-1",
            "amount": 20000,
            "currency": "INR",
            "payment_status": "SUCCESS",
            "gateway_payment_id": "pay_test_001",
            "created_at": "2026-10-01T00:05:00Z",
        }
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = payments

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get("/api/v1/subscriptions/current")
        assert response.status_code == 200
        data = response.json()
        assert data["subscription_status"] == "ACTIVE"
        assert data["can_access_paid_features"] is True
        assert len(data["payments"]) == 1
        assert data["payments"][0]["gateway_payment_id"] == "pay_test_001"
    finally:
        app.dependency_overrides.clear()


# ─── 5. Server-Side Access Control Dependency ─────────────────────────

@pytest.mark.asyncio
async def test_require_active_subscription_allows_active_and_valid_trial():
    """Verify dependency allows access for valid trial and active subscriptions."""
    user = {"id": USER_ID, "email_confirmed": True}
    mock_supabase = MagicMock()

    # 1. Valid future trial
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "TRIAL_ACTIVE",
        "trial_end_date": "2099-01-01T00:00:00Z",
    }
    res = await require_active_subscription(user, mock_supabase)
    assert res == user

    # 2. Active subscriber
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "ACTIVE",
    }
    res = await require_active_subscription(user, mock_supabase)
    assert res == user


@pytest.mark.asyncio
async def test_require_active_subscription_blocks_expired_and_past_due():
    """Verify dependency blocks expired trial and past-due statuses with HTTP 402."""
    user = {"id": USER_ID, "email_confirmed": True}
    mock_supabase = MagicMock()

    # 1. Expired trial
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "TRIAL_ACTIVE",
        "trial_end_date": "2020-01-01T00:00:00Z",  # In the past
    }
    with pytest.raises(HTTPException) as exc1:
        await require_active_subscription(user, mock_supabase)
    assert exc1.value.status_code == 402
    assert "Free trial has expired" in exc1.value.detail

    # 2. Canceled subscription
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "CANCELED",
    }
    with pytest.raises(HTTPException) as exc2:
        await require_active_subscription(user, mock_supabase)
    assert exc2.value.status_code == 402

    # 3. Past due subscription
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "PAST_DUE",
    }
    with pytest.raises(HTTPException) as exc3:
        await require_active_subscription(user, mock_supabase)
    assert exc3.value.status_code == 402


# ─── 6. Subscription Cancellation API (/api/v1/subscriptions/cancel) ─

def test_cancel_subscription_during_trial(mock_user):
    """
    Verify user can cancel their trial before any payment occurs.
    Status transitions to CANCELED, cancellation timestamp is set,
    and no charges are made.
    """
    mock_supabase = MagicMock()
    trial_sub = {
        "id": "sub-to-cancel",
        "user_id": USER_ID,
        "subscription_status": "TRIAL_ACTIVE",
        "gateway_subscription_id": None,
    }
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = trial_sub

    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {"id": "sub-to-cancel", "subscription_status": "CANCELED"}
    ]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "evt-1"}]

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.post("/api/v1/subscriptions/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["cancelled"] is True
        assert data["subscription_status"] == "CANCELED"
        assert "No further charges will be made" in data["message"]
        assert "cancellation_date" in data

        # Verify DB update called
        mock_supabase.table.return_value.update.assert_called()
    finally:
        app.dependency_overrides.clear()


def test_cancel_subscription_already_cancelled_is_idempotent(mock_user):
    """Verify cancellation call is idempotent if already cancelled."""
    mock_supabase = MagicMock()
    already_cancelled_sub = {
        "id": "sub-already-cancelled",
        "user_id": USER_ID,
        "subscription_status": "CANCELED",
        "cancellation_date": "2026-10-20T10:00:00Z",
    }
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = already_cancelled_sub

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.post("/api/v1/subscriptions/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["cancelled"] is True
        assert data["subscription_status"] == "CANCELED"
        assert "already cancelled" in data["message"]
    finally:
        app.dependency_overrides.clear()


def test_cancel_subscription_unauthorized():
    """Verify unauthenticated user cannot cancel subscription."""
    response = client.post("/api/v1/subscriptions/cancel")
    assert response.status_code == 401


# ─── 7. Phase 6 Audit Verification Tests ─────────────────────────────

def test_evaluate_subscription_canceled_retains_paid_access_until_billing_date():
    """
    Audit Check: Canceled paid subscribers retain access until their paid-through date
    (next_billing_date in future).
    """
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Paid subscriber cancelled mid-cycle (10 days remaining in paid month)
    canceled_paid_sub = {
        "subscription_status": "CANCELED",
        "gateway_subscription_id": "sub_Rzp12345",
        "next_billing_date": (now + timedelta(days=10)).isoformat(),
        "cancellation_date": now.isoformat(),
    }
    can_access, status_val, days_left = evaluate_subscription_access(canceled_paid_sub, now)
    assert can_access is True
    assert status_val == "CANCELED"
    assert days_left == 10

    # Once next_billing_date has passed, access terminates
    past_canceled_sub = {
        "subscription_status": "CANCELED",
        "gateway_subscription_id": "sub_Rzp12345",
        "next_billing_date": (now - timedelta(days=1)).isoformat(),
        "cancellation_date": (now - timedelta(days=5)).isoformat(),
    }
    can_access_past, status_past, _ = evaluate_subscription_access(past_canceled_sub, now)
    assert can_access_past is False
    assert status_past == "CANCELED"


def test_past_due_grace_period_exact_72_hour_boundary_conditions():
    """
    Audit Check: Verify exact 72-hour grace period boundary conditions.
    - Immediately before limit (71h 59m): Access GRANTED (PAST_DUE)
    - At exact 72-hour limit (72h 00m): Access GRANTED (PAST_DUE)
    - Immediately after limit (72h 01m): Access DENIED (PAST_DUE)
    - Long after limit (96h): Access DENIED (PAST_DUE)
    All calculations use consistent UTC timestamps.
    """
    failure_time = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    sub = {
        "subscription_status": "PAST_DUE",
        "payment_failed_at": failure_time.isoformat(),
    }

    # 1. Immediately before limit (71 hours, 59 minutes)
    now_before = failure_time + timedelta(hours=71, minutes=59)
    can_access, status_val, _ = evaluate_subscription_access(sub, now_before)
    assert can_access is True
    assert status_val == "PAST_DUE"

    # 2. At exact boundary (72 hours, 00 minutes, 00 seconds)
    now_at = failure_time + timedelta(hours=72)
    can_access_at, status_at, _ = evaluate_subscription_access(sub, now_at)
    assert can_access_at is True
    assert status_at == "PAST_DUE"

    # 3. Immediately after boundary (72 hours, 01 minute)
    now_after = failure_time + timedelta(hours=72, minutes=1)
    can_access_after, status_after, _ = evaluate_subscription_access(sub, now_after)
    assert can_access_after is False
    assert status_after == "PAST_DUE"

    # 4. Long after limit (96 hours)
    now_expired = failure_time + timedelta(hours=96)
    can_access_exp, status_exp, _ = evaluate_subscription_access(sub, now_expired)
    assert can_access_exp is False
    assert status_exp == "PAST_DUE"


def test_multi_layer_trial_abuse_detection():
    """
    Audit Check: Multi-layered trial abuse detection does not rely exclusively
    on email normalization.
    - Layer 1: Normalized email match in profiles.
    - Layer 2: Direct raw email match in profiles.
    - Layer 3: Prior trial event logged in subscription_events.
    - Layer 4: Eligible unique user passes all layers.
    """
    mock_supabase = MagicMock()

    # Layer 1: Normalized email match (e.g. Gmail dot/plus alias evasion)
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {"id": "usr-other-1", "email": "alice@gmail.com", "normalized_email": "alice@gmail.com"}
    ]
    assert check_duplicate_trial_abuse("a.l.i.c.e+tag@gmail.com", USER_ID, mock_supabase) is True

    # Layer 2: Direct exact email match
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {"id": "usr-other-2", "email": "bob@customcorp.com"}
    ]
    assert check_duplicate_trial_abuse("bob@customcorp.com", USER_ID, mock_supabase) is True

    # Layer 3: Audit event log match in subscription_events
    # Reset profiles to empty
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
    # Event logs have prior duplicate attempt recorded
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": "evt-prior-99",
            "event_type": "TRIAL_DUPLICATE_PREVENTED",
            "payload": {"normalized_email": "charlie@hospital.org", "user_id": "usr-prior-3"},
        }
    ]
    assert check_duplicate_trial_abuse("charlie@hospital.org", USER_ID, mock_supabase) is True

    # Layer 4: Brand new eligible user — no matches in any layer
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    assert check_duplicate_trial_abuse("fresh.unique.patient@newdomain.com", USER_ID, mock_supabase) is False


def test_email_normalization_provider_matrix():
    """
    Audit Check: Verification across Gmail, Googlemail, Yahoo, Outlook, and unknown providers.
    - Gmail / Googlemail: dots and plus tags stripped, domains unified.
    - Yahoo, Outlook, Unknown: dots and plus tags strictly preserved.
    """
    # 1. Gmail
    assert normalize_email("Test.User+Trial1@gmail.com") == "testuser@gmail.com"
    # 2. Googlemail
    assert normalize_email("Test.User+Trial2@googlemail.com") == "testuser@gmail.com"
    # 3. Yahoo (dots & plus-tags preserved)
    assert normalize_email("Test.User+Trial3@yahoo.com") == "test.user+trial3@yahoo.com"
    # 4. Outlook (dots & plus-tags preserved)
    assert normalize_email("Test.User+Trial4@outlook.com") == "test.user+trial4@outlook.com"
    # 5. Unknown provider / enterprise domain (dots & plus-tags preserved)
    assert normalize_email("Clinical.Lead+Oncology@st-jude.health.org.uk") == "clinical.lead+oncology@st-jude.health.org.uk"


@pytest.mark.asyncio
async def test_require_active_subscription_allows_canceled_within_paid_period():
    """
    Audit Check: require_active_subscription dependency allows canceled paid user
    while still within their paid period.
    """
    user = {"id": USER_ID, "email_confirmed": True}
    mock_supabase = MagicMock()
    now = datetime.now(timezone.utc)

    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "CANCELED",
        "gateway_subscription_id": "sub_Rzp12345",
        "next_billing_date": (now + timedelta(days=7)).isoformat(),
    }
    res = await require_active_subscription(user, mock_supabase)
    assert res == user


@pytest.mark.asyncio
async def test_require_active_subscription_blocks_past_due_after_72_hours():
    """
    Audit Check: require_active_subscription blocks PAST_DUE user once the 72-hour
    grace period has elapsed.
    """
    user = {"id": USER_ID, "email_confirmed": True}
    mock_supabase = MagicMock()
    now = datetime.now(timezone.utc)

    # 73 hours ago (grace period expired)
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "PAST_DUE",
        "payment_failed_at": (now - timedelta(hours=73)).isoformat(),
    }
    with pytest.raises(HTTPException) as exc:
        await require_active_subscription(user, mock_supabase)
    assert exc.value.status_code == 402
    assert "PAST_DUE" in exc.value.detail


