"""
MediExplain AI — Trial and Subscription Management Service
Handles trial period calculations, email normalization for abuse prevention,
canonical subscription status mapping, and server-side access enforcement.
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from supabase import Client


CANONICAL_STATUS_MAP = {
    # Active trial
    "TRIAL_ACTIVE": "TRIAL_ACTIVE",
    # Active paid subscription
    "ACTIVE": "ACTIVE",
    "AUTHENTICATED": "ACTIVE",
    # Payment failures / grace period
    "PAST_DUE": "PAST_DUE",
    "PAYMENT_PENDING": "PAST_DUE",
    "PAYMENT_FAILED": "PAST_DUE",
    "HALTED": "PAST_DUE",
    # User / system cancellation
    "CANCELED": "CANCELED",
    "CANCELLED": "CANCELED",
    # Expiration
    "EXPIRED": "EXPIRED",
    "TRIAL_EXPIRED": "EXPIRED",
    "COMPLETED": "EXPIRED",
    # Authorization pending
    "AUTHORIZATION_PENDING": "TRIAL_ACTIVE",
}


def normalize_email(email: str) -> str:
    """
    Normalize email address for duplicate account and trial abuse detection:
    - Gmail / Googlemail: dots removed, plus-tags removed, domain unified to 'gmail.com'.
    - Non-Gmail (Yahoo, Outlook, custom, and unknown providers):
      Preserve email address exactly (case-lowered and trimmed), retaining all dots and plus-tags.
    """
    if not email or "@" not in email:
        return (email or "").strip().lower()

    clean_email = email.strip().lower()
    local_part, domain = clean_email.split("@", 1)

    # Restrict dot and plus-tag normalization strictly to Gmail / Googlemail
    if domain in ("gmail.com", "googlemail.com"):
        local_part = local_part.replace(".", "")
        local_part = local_part.split("+")[0]
        domain = "gmail.com"
        return f"{local_part}@{domain}"

    # For all non-Gmail providers, preserve the email address exactly (dots and plus-tags kept)
    return clean_email


def calculate_trial_period(
    start_time: Optional[datetime] = None,
    days: int = 30
) -> Tuple[datetime, datetime]:
    """
    Calculate trial start and expiration timestamps using UTC server time.
    Ensures strict 30 calendar day duration.
    """
    start = start_time or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = start + timedelta(days=days)
    return start, end


def parse_utc_timestamp(ts: str | datetime | None) -> Optional[datetime]:
    """Parse ISO timestamp or return datetime in UTC."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        cleaned = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def get_trial_days_remaining(
    trial_end_date: str | datetime | None,
    current_time: Optional[datetime] = None
) -> int:
    """
    Calculate full calendar days remaining in trial.
    Returns 0 if already passed or not set.
    """
    end = parse_utc_timestamp(trial_end_date)
    if not end:
        return 0
    now = current_time or datetime.now(timezone.utc)
    delta = end - now
    if delta.total_seconds() <= 0:
        return 0
    return max(0, int(delta.total_seconds() // 86400))


def evaluate_subscription_access(
    subscription: dict,
    current_time: Optional[datetime] = None
) -> Tuple[bool, str, int]:
    """
    Evaluate server-side whether a subscription grants access to paid features.
    
    Returns:
        (can_access: bool, canonical_status: str, days_remaining: int)
    """
    raw_status = (subscription.get("subscription_status") or "EXPIRED").upper()
    canonical_status = CANONICAL_STATUS_MAP.get(raw_status, "EXPIRED")
    now = current_time or datetime.now(timezone.utc)

    days_remaining = get_trial_days_remaining(subscription.get("trial_end_date"), now)

    # 1. Active paid subscriber
    if canonical_status == "ACTIVE":
        return True, "ACTIVE", 0

    # 2. Trial active
    if canonical_status == "TRIAL_ACTIVE":
        trial_end = parse_utc_timestamp(subscription.get("trial_end_date"))
        if trial_end and now <= trial_end:
            return True, "TRIAL_ACTIVE", days_remaining
        # Trial timestamp has passed in real time
        return False, "EXPIRED", 0

    # 3. Canceled subscription with paid-through access retention
    if canonical_status == "CANCELED":
        next_billing = parse_utc_timestamp(subscription.get("next_billing_date"))
        has_gateway = bool(subscription.get("gateway_subscription_id"))
        if has_gateway and next_billing and now <= next_billing:
            paid_days_left = max(0, int((next_billing - now).total_seconds() // 86400))
            return True, "CANCELED", paid_days_left
        return False, "CANCELED", 0

    # 4. Past Due subscription with configured exactly 72-hour grace period
    if canonical_status == "PAST_DUE":
        from app.core.config import settings
        grace_hours = getattr(settings, "GRACE_PERIOD_HOURS", 72)
        failure_time = (
            parse_utc_timestamp(subscription.get("payment_failed_at"))
            or parse_utc_timestamp(subscription.get("updated_at"))
            or parse_utc_timestamp(subscription.get("next_billing_date"))
        )
        if grace_hours > 0 and failure_time:
            # Policy is exactly 72 hours in UTC
            grace_expiry = failure_time + timedelta(hours=grace_hours)
            if now <= grace_expiry:
                hours_left = max(0, int((grace_expiry - now).total_seconds() // 3600))
                days_left = max(0, int((grace_expiry - now).total_seconds() // 86400))
                return True, "PAST_DUE", days_left
        return False, "PAST_DUE", 0

    # 5. All other states (EXPIRED, etc.)
    return False, canonical_status, 0


def check_duplicate_trial_abuse(
    email: str,
    user_id: str,
    supabase: Client
) -> bool:
    """
    Multi-layered trial abuse detection:
    Layer 1: Normalized email match in profiles (for Gmail / Googlemail alias detection).
    Layer 2: Exact case-insensitive email match in profiles across other accounts.
    Layer 3: Previous trial event audit check in subscription_events.
    Returns True if duplicate account or prior trial usage is detected, False if eligible.
    """
    norm_email = normalize_email(email)
    raw_email = (email or "").strip().lower()

    try:
        # Layer 1: Check normalized email match (for Gmail alias evasion)
        res_norm = (
            supabase.table("profiles")
            .select("id, email, normalized_email")
            .eq("normalized_email", norm_email)
            .neq("id", user_id)
            .execute()
        )
        if res_norm.data and len(res_norm.data) > 0:
            return True

        # Layer 2: Check exact email match
        if raw_email:
            res_exact = (
                supabase.table("profiles")
                .select("id, email")
                .eq("email", raw_email)
                .neq("id", user_id)
                .execute()
            )
            if res_exact.data and len(res_exact.data) > 0:
                return True

        # Layer 3: Check trial event logs for prior granted trials matching normalized email
        try:
            res_events = (
                supabase.table("subscription_events")
                .select("id, payload")
                .eq("event_type", "TRIAL_DUPLICATE_PREVENTED")
                .execute()
            )
            if res_events.data:
                for evt in res_events.data:
                    p = evt.get("payload") or {}
                    if p.get("normalized_email") == norm_email and p.get("user_id") != user_id:
                        return True
        except Exception:
            pass

        return False
    except Exception:
        # Fail safe: don't crash, return False if query fails
        return False

