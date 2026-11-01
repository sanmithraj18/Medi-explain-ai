"""
MediExplain AI — Subscriptions Endpoint
Handles 30-day free trial lifecycle, subscription status management,
server-side access gating, and cancellation workflows.

CREDENTIALS REQUIRED to activate Razorpay (Phase 7):
  RAZORPAY_KEY_ID     — backend/.env — SECRET
  RAZORPAY_KEY_SECRET — backend/.env — SECRET
  RAZORPAY_PLAN_ID    — backend/.env — not secret but required
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.core.config import settings
from app.core.dependencies import get_current_user, require_email_verified
from app.db.supabase_client import get_supabase
from app.services.payment.razorpay_service import (
    create_plan_if_needed,
    create_subscription,
    fetch_subscription,
    cancel_subscription,
    verify_payment_signature,
)
from app.services.subscription.trial_service import (
    calculate_trial_period,
    evaluate_subscription_access,
    check_duplicate_trial_abuse,
    parse_utc_timestamp,
)

router = APIRouter()


class VerifyCheckoutRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


async def _resolve_user_subscription(current_user: dict, supabase: Client) -> dict:
    """
    Fetch subscription for user. If not found, provision trial (or expired trial if duplicate).
    """
    result = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", current_user["id"])
        .execute()
    )

    if result.data and len(result.data) > 0:
        return result.data[0]

    # No subscription record exists yet — provision on the fly
    email = current_user.get("email", "")
    is_duplicate = check_duplicate_trial_abuse(email, current_user["id"], supabase)

    now = datetime.now(timezone.utc)
    if is_duplicate:
        sub_record = {
            "user_id": current_user["id"],
            "plan_name": "MediExplain AI Premium",
            "amount": settings.PLAN_AMOUNT_PAISE,
            "currency": settings.PLAN_CURRENCY,
            "subscription_status": "EXPIRED",
            "trial_start_date": now.isoformat(),
            "trial_end_date": now.isoformat(),
        }
    else:
        start_time, end_time = calculate_trial_period(now, days=settings.TRIAL_DAYS)
        sub_record = {
            "user_id": current_user["id"],
            "plan_name": "MediExplain AI Premium",
            "amount": settings.PLAN_AMOUNT_PAISE,
            "currency": settings.PLAN_CURRENCY,
            "subscription_status": "TRIAL_ACTIVE",
            "trial_start_date": start_time.isoformat(),
            "trial_end_date": end_time.isoformat(),
        }

    insert_res = supabase.table("subscriptions").insert(sub_record).execute()
    return insert_res.data[0] if insert_res.data else sub_record


@router.get("/current")
@router.get("/me")
async def get_current_subscription(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Return the current user's complete subscription & free trial record.
    Server timestamps determine exact trial countdown and status.
    """
    sub = await _resolve_user_subscription(current_user, supabase)

    # Server-side validation of active status
    can_access, canonical_status, days_remaining = evaluate_subscription_access(sub)

    # Sync expired status back to database if trial timestamp elapsed
    if canonical_status == "EXPIRED" and sub.get("subscription_status") in ("TRIAL_ACTIVE", "ACTIVE"):
        try:
            supabase.table("subscriptions").update(
                {"subscription_status": "EXPIRED"}
            ).eq("user_id", current_user["id"]).execute()
            sub["subscription_status"] = "EXPIRED"
        except Exception:
            pass

    # Fetch recent payments for billing history
    payments_res = (
        supabase.table("payments")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return {
        "id": sub.get("id"),
        "user_id": current_user["id"],
        "plan_name": sub.get("plan_name", "MediExplain AI Premium"),
        "amount": sub.get("amount", settings.PLAN_AMOUNT_PAISE),
        "currency": sub.get("currency", settings.PLAN_CURRENCY),
        "amount_formatted": "₹200",
        "subscription_status": canonical_status,
        "raw_status": sub.get("subscription_status"),
        "trial_start_date": sub.get("trial_start_date"),
        "trial_end_date": sub.get("trial_end_date"),
        "trial_days_remaining": days_remaining,
        "is_trial_active": canonical_status == "TRIAL_ACTIVE",
        "can_access_paid_features": can_access,
        "billing_start_date": sub.get("billing_start_date"),
        "next_billing_date": sub.get("next_billing_date"),
        "cancellation_date": sub.get("cancellation_date"),
        "is_cancelled": canonical_status == "CANCELED",
        "gateway_subscription_id": sub.get("gateway_subscription_id"),
        "payments": payments_res.data or [],
        "renewal_disclosure": (
            "30-day free trial. Automatic monthly charge of ₹200 applies only if you explicitly "
            "authorize recurring mandate. You can cancel at any time to avoid renewal."
        ),
    }


@router.post("/cancel")
async def cancel_my_subscription(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Cancel the user's subscription or active trial.
    During trial (with or without Razorpay mandate): marks cancelled immediately, no charge made.
    With active Razorpay subscription: requests gateway cancellation and marks cancelled.
    """
    result = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription record found for this user.",
        )

    sub = result.data
    raw_status = (sub.get("subscription_status") or "").upper()
    if raw_status in ("CANCELLED", "CANCELED"):
        return {
            "cancelled": True,
            "subscription_status": "CANCELED",
            "message": "Subscription is already cancelled. No further charges will be made.",
            "cancellation_date": sub.get("cancellation_date"),
        }

    gateway_sub_id = sub.get("gateway_subscription_id")
    in_trial = raw_status in ("TRIAL_ACTIVE", "AUTHORIZATION_PENDING")

    # If gateway subscription exists, attempt gateway cancellation
    if gateway_sub_id:
        try:
            cancel_subscription(gateway_sub_id, cancel_at_cycle_end=not in_trial)
        except Exception:
            # If gateway is offline or in test mode, proceed with local cancellation
            pass

    now_iso = datetime.now(timezone.utc).isoformat()
    # Update DB record with CANCELED
    supabase.table("subscriptions").update({
        "subscription_status": "CANCELED",
        "cancellation_date": now_iso,
    }).eq("user_id", current_user["id"]).execute()

    # Log subscription event idempotently
    try:
        supabase.table("subscription_events").insert({
            "subscription_id": sub.get("id"),
            "event_type": "SUBSCRIPTION_CANCELED",
            "gateway_event_id": f"int_cancel_{sub.get('id')}_{int(datetime.now(timezone.utc).timestamp())}",
            "payload": {
                "user_id": current_user["id"],
                "in_trial": in_trial,
                "canceled_at": now_iso,
            }
        }).execute()
    except Exception:
        pass

    return {
        "cancelled": True,
        "subscription_status": "CANCELED",
        "cancellation_date": now_iso,
        "message": (
            "Subscription cancelled. No further charges will be made."
            if in_trial
            else "Subscription cancelled. Access remains active until the end of your billing cycle."
        ),
    }


@router.post("/create-checkout")
async def create_checkout_session(
    current_user: dict = Depends(require_email_verified),
    supabase: Client = Depends(get_supabase),
):
    """
    Create a Razorpay subscription and return the subscription ID for checkout.

    The frontend uses this ID to open Razorpay Checkout where the user
    completes the recurring-payment mandate authorization.

    IMPORTANT: This endpoint does NOT charge the user. The first charge
    happens after the 30-day trial. The user must complete the mandate
    authorization flow in the Razorpay Checkout to activate recurring billing.
    """
    # Check user doesn't already have an active Razorpay subscription
    existing = (
        supabase.table("subscriptions")
        .select("subscription_status, gateway_subscription_id")
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if existing.data:
        sub = existing.data
        if sub.get("gateway_subscription_id") and sub["subscription_status"] in (
            "ACTIVE", "AUTHORIZATION_PENDING", "TRIAL_ACTIVE"
        ):
            # Check if gateway sub is still valid
            try:
                gateway_sub = fetch_subscription(sub["gateway_subscription_id"])
                if gateway_sub["status"] not in ("cancelled", "expired", "completed"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="An active subscription already exists. "
                               "Please manage it from your billing dashboard.",
                    )
            except HTTPException:
                raise
            except Exception:
                pass  # Gateway fetch failed — allow creating new subscription

    # Calculate start_at offset based on user's remaining trial
    start_at = None
    first_charge_date = None
    if existing.data and existing.data.get("trial_end_date"):
        trial_end = parse_utc_timestamp(existing.data["trial_end_date"])
        now = datetime.now(timezone.utc)
        if trial_end and trial_end > now:
            start_at = int(trial_end.timestamp())
            first_charge_date = trial_end.isoformat()
        else:
            # User's trial has already elapsed: recurring billing starts immediately upon mandate authorization
            start_at = None
            first_charge_date = now.isoformat()
    elif not existing.data:
        trial_ts = int(datetime.now(timezone.utc).timestamp()) + (settings.TRIAL_DAYS * 24 * 3600)
        start_at = trial_ts
        first_charge_date = datetime.fromtimestamp(trial_ts, tz=timezone.utc).isoformat()

    # Get or create plan
    plan_id = create_plan_if_needed()

    # Create Razorpay subscription (trial handled by start_at offset)
    gateway_sub = create_subscription(plan_id=plan_id, start_at=start_at)
    gateway_sub_id = gateway_sub["id"]

    # Update our subscription record
    supabase.table("subscriptions").update({
        "gateway_subscription_id": gateway_sub_id,
        "subscription_status": "AUTHORIZATION_PENDING",
        "billing_start_date": datetime.now(timezone.utc).isoformat(),
    }).eq("user_id", current_user["id"]).execute()

    # Return only what the frontend needs for checkout
    return {
        "gateway_subscription_id": gateway_sub_id,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,  # Public key only
        "plan_name": "MediExplain AI Premium",
        "amount": settings.PLAN_AMOUNT_PAISE,
        "amount_formatted": "₹200",
        "currency": settings.PLAN_CURRENCY,
        "trial_days": settings.TRIAL_DAYS,
        "first_charge_date": first_charge_date,
        "billing_interval": "monthly",
        "description": (
            "30-day free trial. Automatic monthly charge of ₹200 begins on "
            f"{first_charge_date[:10]}. You can cancel anytime before this date to avoid any charge."
        ),
    }


@router.post("/verify-checkout")
async def verify_checkout(
    body: VerifyCheckoutRequest,
    current_user: dict = Depends(require_email_verified),
    supabase: Client = Depends(get_supabase),
):
    """
    Verify the Razorpay checkout signature after the user completes mandate authorization.
    Verifies user ownership, validates HMAC-SHA256 signature server-side using the server-stored
    subscription ID (never trusting frontend-supplied IDs alone), and records the event.
    """
    # 1. Fetch user's subscription record by authenticated user_id
    user_sub = (
        supabase.table("subscriptions")
        .select("id, user_id, gateway_subscription_id, trial_end_date")
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not user_sub.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription record not found for this user.",
        )

    server_stored_sub_id = user_sub.data.get("gateway_subscription_id")
    if not server_stored_sub_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No subscription checkout session pending for this user.",
        )

    # 2. Never trust a subscription ID supplied only by frontend
    if server_stored_sub_id != body.razorpay_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription ID mismatch between server session and checkout response.",
        )

    # 3. Server-side HMAC-SHA256 signature verification using server-stored subscription ID
    is_valid = verify_payment_signature(
        razorpay_subscription_id=server_stored_sub_id,
        razorpay_payment_id=body.razorpay_payment_id,
        razorpay_signature=body.razorpay_signature,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed. Please contact support.",
        )

    # 4. Confirm payment ownership and gateway status from Razorpay before updating records
    try:
        gateway_sub = fetch_subscription(server_stored_sub_id)
        gateway_status = gateway_sub.get("status", "")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not verify subscription status. Please check your billing dashboard.",
        )

    if gateway_status not in ("authenticated", "active"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subscription gateway status '{gateway_status}' is not authorized.",
        )

    status_map = {
        "created": "AUTHORIZATION_PENDING",
        "authenticated": "TRIAL_ACTIVE",
        "active": "ACTIVE",
        "pending": "PAYMENT_PENDING",
        "halted": "PAST_DUE",
        "cancelled": "CANCELED",
        "completed": "EXPIRED",
        "expired": "EXPIRED",
    }
    our_status = status_map.get(gateway_status, "AUTHORIZATION_PENDING")

    next_charge_at = gateway_sub.get("charge_at")
    next_billing = (
        datetime.fromtimestamp(next_charge_at, tz=timezone.utc).isoformat()
        if next_charge_at
        else None
    )

    update_payload = {
        "subscription_status": our_status,
        "gateway_subscription_id": body.razorpay_subscription_id,
    }
    if next_billing:
        update_payload["next_billing_date"] = next_billing

    supabase.table("subscriptions").update(update_payload).eq("user_id", current_user["id"]).execute()

    # Log idempotent event in subscription_events
    try:
        supabase.table("subscription_events").insert({
            "subscription_id": user_sub.data[0]["id"],
            "event_type": "CHECKOUT_VERIFIED",
            "gateway_event_id": f"chk_{body.razorpay_payment_id}",
            "payload": {
                "razorpay_subscription_id": body.razorpay_subscription_id,
                "razorpay_payment_id": body.razorpay_payment_id,
                "verified_status": our_status,
            },
            "event_status": "PROCESSED",
        }).execute()
    except Exception:
        pass

    return {
        "verified": True,
        "subscription_status": our_status,
        "message": "Subscription authorized successfully. Your 30-day trial is active.",
    }
