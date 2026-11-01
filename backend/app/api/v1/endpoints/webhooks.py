"""
MediExplain AI — Razorpay Webhook Endpoint
SECURITY CRITICAL: Every incoming webhook is signature-verified using HMAC-SHA256
before any business logic or database state updates are processed.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException, Request, status, Depends
from supabase import Client

from app.core.limiter import limiter
from app.core.config import settings
from app.db.supabase_client import get_supabase
from app.services.subscription.trial_service import evaluate_subscription_access

router = APIRouter()

SUPPORTED_EVENTS = {
    "subscription.authenticated",
    "subscription.activated",
    "subscription.pending",
    "subscription.halted",
    "subscription.cancelled",
    "subscription.charged",
    "payment.authorized",
    "payment.captured",
    "payment.failed",
}


def _verify_razorpay_signature(raw_body: bytes, signature: str) -> bool:
    """
    Verify Razorpay webhook signature using HMAC-SHA256.
    Returns True only if the computed signature matches the header value.
    Never allow unsigned webhooks to update payment or subscription state.
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured",
        )
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/razorpay", status_code=200)
@router.post("/razorpay/webhook", status_code=200)
@limiter.limit("60/minute")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    x_razorpay_event_id: str | None = Header(default=None, alias="X-Razorpay-Event-Id"),
    supabase: Client = Depends(get_supabase),
):
    """
    Razorpay webhook receiver.
    Pipeline:
      1. Read raw body (before any JSON parsing)
      2. Verify HMAC-SHA256 signature using X-Razorpay-Signature
      3. Verify X-Razorpay-Event-Id request header against payload
      4. Validate event type and format
      5. Enforce idempotency (gateway_event_id unique check in subscription_events)
      6. Process event and update database
      7. Return HTTP 200 acknowledgment (Razorpay retries on non-2xx)
    """
    # Step 1: Read raw body
    raw_body = await request.body()

    # Step 2: Verify signature on raw request body
    if not x_razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header",
        )
    if not _verify_razorpay_signature(raw_body, x_razorpay_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature verification failed",
        )

    # Step 3: Parse JSON payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = payload.get("event")
    payload_event_id = payload.get("id")         # Razorpay event ID (unique per webhook)
    header_event_id = x_razorpay_event_id or request.headers.get("x-razorpay-event-id")

    # Verify event ID header matches payload ID if both are supplied
    if header_event_id and payload_event_id and header_event_id != payload_event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Razorpay-Event-Id header does not match payload event id",
        )

    event_id = header_event_id or payload_event_id

    if not event_type or not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event type or event ID",
        )

    # Step 4: Check idempotency — ignore already-processed events
    existing = (
        supabase.table("subscription_events")
        .select("id, event_status")
        .eq("gateway_event_id", event_id)
        .execute()
    )
    if existing.data and len(existing.data) > 0:
        # Already processed — return 200 so Razorpay stops retrying
        return {"status": "duplicate_ignored"}

    # Base event log record
    event_log = {
        "event_type": event_type,
        "gateway_event_id": event_id,
        "payload": payload,
        "event_status": "PROCESSED",
    }

    # Step 5: Route to specific handler
    if event_type not in SUPPORTED_EVENTS:
        event_log["event_status"] = "PROCESSED"
        supabase.table("subscription_events").insert(event_log).execute()
        return {"status": "unsupported_event_acknowledged"}

    try:
        await _dispatch_event(event_type, payload, supabase, event_log)
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "duplicate" in err_str or "23505" in err_str:
            return {"status": "duplicate_ignored"}
        event_log["event_status"] = "FAILED"
        try:
            supabase.table("subscription_events").insert(event_log).execute()
        except Exception:
            pass
        # Return 200 to prevent Razorpay infinite retries on downstream database errors
        return {"status": "processing_error", "detail": str(e)}

    return {"status": "ok"}


async def _dispatch_event(
    event_type: str, payload: dict, supabase: Client, event_log: dict
):
    """Route to the correct handler based on event type."""
    entity = payload.get("payload", {})

    if event_type == "subscription.authenticated":
        await _handle_subscription_authenticated(entity, supabase, event_log)

    elif event_type == "subscription.activated":
        await _handle_subscription_activated(entity, supabase, event_log)

    elif event_type == "subscription.charged":
        await _handle_subscription_charged(entity, supabase, event_log)

    elif event_type == "subscription.halted":
        await _handle_subscription_halted(entity, supabase, event_log)

    elif event_type == "subscription.cancelled":
        await _handle_subscription_cancelled(entity, supabase, event_log)

    elif event_type == "payment.failed":
        await _handle_payment_failed(entity, supabase, event_log)

    elif event_type == "payment.captured":
        await _handle_payment_captured(entity, supabase, event_log)

    else:
        supabase.table("subscription_events").insert(event_log).execute()


async def _get_subscription_by_gateway_id(
    gateway_sub_id: str, supabase: Client
) -> dict | None:
    """Fetch subscription record by Razorpay subscription ID."""
    result = (
        supabase.table("subscriptions")
        .select("*")
        .eq("gateway_subscription_id", gateway_sub_id)
        .execute()
    )
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


async def _handle_subscription_authenticated(
    entity: dict, supabase: Client, event_log: dict
):
    """
    Mandate registration completed by customer via Razorpay checkout (UPI Autopay / Card).
    Preserves free trial if trial is still active, or transitions to ACTIVE if trial concluded.
    """
    sub_entity = entity.get("subscription", {}).get("entity", {})
    gateway_sub_id = sub_entity.get("id")
    if not gateway_sub_id:
        return

    sub = await _get_subscription_by_gateway_id(gateway_sub_id, supabase)
    if sub:
        event_log["subscription_id"] = sub["id"]
        can_access, canonical_status, _ = evaluate_subscription_access(sub)

        next_charge_at = sub_entity.get("charge_at")
        next_billing = (
            datetime.fromtimestamp(next_charge_at, tz=timezone.utc).isoformat()
            if next_charge_at
            else None
        )
        new_status = "TRIAL_ACTIVE" if canonical_status == "TRIAL_ACTIVE" else "ACTIVE"

        updates = {
            "subscription_status": new_status,
            "gateway_subscription_id": gateway_sub_id,
        }
        if next_billing:
            updates["next_billing_date"] = next_billing

        supabase.table("subscriptions").update(updates).eq("id", sub["id"]).execute()

    supabase.table("subscription_events").insert(event_log).execute()


async def _handle_subscription_activated(
    entity: dict, supabase: Client, event_log: dict
):
    """Subscription has officially begun recurring billing."""
    sub_entity = entity.get("subscription", {}).get("entity", {})
    gateway_sub_id = sub_entity.get("id")
    if not gateway_sub_id:
        return

    sub = await _get_subscription_by_gateway_id(gateway_sub_id, supabase)
    if sub:
        event_log["subscription_id"] = sub["id"]
        next_charge_at = sub_entity.get("charge_at")
        next_billing = (
            datetime.fromtimestamp(next_charge_at, tz=timezone.utc).isoformat()
            if next_charge_at
            else None
        )
        supabase.table("subscriptions").update({
            "subscription_status": "ACTIVE",
            "next_billing_date": next_billing,
        }).eq("id", sub["id"]).execute()

    supabase.table("subscription_events").insert(event_log).execute()


async def _handle_subscription_charged(
    entity: dict, supabase: Client, event_log: dict
):
    """
    Successful recurring monthly debit.
    - Sets subscription status to ACTIVE.
    - Updates next_billing_date.
    - Idempotently creates payment record in payments table.
    """
    sub_entity = entity.get("subscription", {}).get("entity", {})
    payment_entity = entity.get("payment", {}).get("entity", {})
    gateway_sub_id = sub_entity.get("id")
    if not gateway_sub_id:
        return

    sub = await _get_subscription_by_gateway_id(gateway_sub_id, supabase)
    if sub:
        event_log["subscription_id"] = sub["id"]

        next_charge_at = sub_entity.get("charge_at")
        next_billing = (
            datetime.fromtimestamp(next_charge_at, tz=timezone.utc).isoformat()
            if next_charge_at
            else None
        )
        supabase.table("subscriptions").update({
            "subscription_status": "ACTIVE",
            "next_billing_date": next_billing,
        }).eq("id", sub["id"]).execute()

        # Idempotently record captured payment
        payment_id = payment_entity.get("id")
        if payment_id:
            existing_pay = (
                supabase.table("payments")
                .select("id")
                .eq("gateway_payment_id", payment_id)
                .execute()
            )
            if not existing_pay.data:
                supabase.table("payments").insert({
                    "user_id": sub["user_id"],
                    "subscription_id": sub["id"],
                    "gateway_payment_id": payment_id,
                    "gateway_order_id": payment_entity.get("order_id"),
                    "amount": payment_entity.get("amount", settings.PLAN_AMOUNT_PAISE),
                    "currency": payment_entity.get("currency", "INR"),
                    "payment_status": "CAPTURED",
                    "payment_method": payment_entity.get("method"),
                    "payment_date": datetime.now(timezone.utc).isoformat(),
                }).execute()

    supabase.table("subscription_events").insert(event_log).execute()


async def _handle_subscription_halted(
    entity: dict, supabase: Client, event_log: dict
):
    """
    Payment retries exhausted. Subscription is halted.
    Transitions status to PAST_DUE and records failure timestamp.
    """
    sub_entity = entity.get("subscription", {}).get("entity", {})
    gateway_sub_id = sub_entity.get("id")
    if not gateway_sub_id:
        return

    sub = await _get_subscription_by_gateway_id(gateway_sub_id, supabase)
    if sub:
        event_log["subscription_id"] = sub["id"]
        now_iso = datetime.now(timezone.utc).isoformat()
        supabase.table("subscriptions").update({
            "subscription_status": "PAST_DUE",
            "updated_at": now_iso,
        }).eq("id", sub["id"]).execute()

    supabase.table("subscription_events").insert(event_log).execute()


async def _handle_subscription_cancelled(
    entity: dict, supabase: Client, event_log: dict
):
    """Subscription canceled by customer or provider."""
    sub_entity = entity.get("subscription", {}).get("entity", {})
    gateway_sub_id = sub_entity.get("id")
    if not gateway_sub_id:
        return

    sub = await _get_subscription_by_gateway_id(gateway_sub_id, supabase)
    if sub:
        event_log["subscription_id"] = sub["id"]
        now_iso = datetime.now(timezone.utc).isoformat()
        supabase.table("subscriptions").update({
            "subscription_status": "CANCELED",
            "cancellation_date": now_iso,
        }).eq("id", sub["id"]).execute()

    supabase.table("subscription_events").insert(event_log).execute()


async def _handle_payment_failed(
    entity: dict, supabase: Client, event_log: dict
):
    """
    Debit transaction failure.
    - Transitions subscription to PAST_DUE with timestamp.
    - Idempotently logs FAILED record in payments table.
    """
    payment_entity = entity.get("payment", {}).get("entity", {})
    gateway_sub_id = payment_entity.get("subscription_id")

    if gateway_sub_id:
        sub = await _get_subscription_by_gateway_id(gateway_sub_id, supabase)
        if sub:
            event_log["subscription_id"] = sub["id"]
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("subscriptions").update({
                "subscription_status": "PAST_DUE",
                "updated_at": now_iso,
            }).eq("id", sub["id"]).execute()

            payment_id = payment_entity.get("id")
            if payment_id:
                existing_pay = (
                    supabase.table("payments")
                    .select("id")
                    .eq("gateway_payment_id", payment_id)
                    .execute()
                )
                if not existing_pay.data:
                    supabase.table("payments").insert({
                        "user_id": sub["user_id"],
                        "subscription_id": sub["id"],
                        "gateway_payment_id": payment_id,
                        "gateway_order_id": payment_entity.get("order_id"),
                        "amount": payment_entity.get("amount", settings.PLAN_AMOUNT_PAISE),
                        "currency": payment_entity.get("currency", "INR"),
                        "payment_status": "FAILED",
                        "payment_method": payment_entity.get("method"),
                        "payment_date": now_iso,
                    }).execute()

    supabase.table("subscription_events").insert(event_log).execute()


async def _handle_payment_captured(
    entity: dict, supabase: Client, event_log: dict
):
    """Individual payment capture event."""
    payment_entity = entity.get("payment", {}).get("entity", {})
    payment_id = payment_entity.get("id")
    if not payment_id:
        supabase.table("subscription_events").insert(event_log).execute()
        return

    existing_payment = (
        supabase.table("payments")
        .select("id")
        .eq("gateway_payment_id", payment_id)
        .execute()
    )
    if not existing_payment.data:
        gateway_sub_id = payment_entity.get("subscription_id")
        sub = (
            await _get_subscription_by_gateway_id(gateway_sub_id, supabase)
            if gateway_sub_id
            else None
        )
        supabase.table("payments").insert({
            "user_id": sub["user_id"] if sub else None,
            "subscription_id": sub["id"] if sub else None,
            "gateway_payment_id": payment_id,
            "gateway_order_id": payment_entity.get("order_id"),
            "amount": payment_entity.get("amount", 0),
            "currency": payment_entity.get("currency", "INR"),
            "payment_status": "CAPTURED",
            "payment_method": payment_entity.get("method"),
            "payment_date": datetime.now(timezone.utc).isoformat(),
        }).execute()

    supabase.table("subscription_events").insert(event_log).execute()
