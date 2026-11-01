"""
MediExplain AI — Razorpay Payment Service

CREDENTIALS REQUIRED (both server-side only, never frontend):
  RAZORPAY_KEY_ID     — backend/.env    (used for API calls)
  RAZORPAY_KEY_SECRET — backend/.env    (used for API auth + signature verify)
  RAZORPAY_PLAN_ID    — backend/.env    (created once, reused)

Never pass RAZORPAY_KEY_SECRET or RAZORPAY_WEBHOOK_SECRET to frontend.
Only RAZORPAY_KEY_ID is safe to expose as NEXT_PUBLIC_.
"""
import hashlib
import hmac

import razorpay
from fastapi import HTTPException, status

from app.core.config import settings

_client = None


def _get_client() -> razorpay.Client:
    global _client
    if _client is None:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service is not configured.",
            )
        _client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
    return _client


def create_plan_if_needed() -> str:
    """
    Create the Razorpay plan if RAZORPAY_PLAN_ID is not set.
    In production, create the plan once and store the ID in .env.
    Returns the plan ID.
    """
    if settings.RAZORPAY_PLAN_ID:
        return settings.RAZORPAY_PLAN_ID

    client = _get_client()
    try:
        plan = client.plan.create({
            "period": "monthly",
            "interval": 1,
            "item": {
                "name": "MediExplain AI Premium",
                "amount": settings.PLAN_AMOUNT_PAISE,
                "currency": settings.PLAN_CURRENCY,
                "description": "Monthly subscription to MediExplain AI Premium",
            },
            "notes": {
                "service": "mediexplain-ai",
            },
        })
        plan_id = plan["id"]
        # Log prominently — operator must save this to .env
        print(f"\n{'='*60}")
        print(f"RAZORPAY PLAN CREATED: {plan_id}")
        print(f"Save this as RAZORPAY_PLAN_ID in your .env file.")
        print(f"{'='*60}\n")
        return plan_id
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to create Razorpay plan: {e}",
        )


def create_subscription(
    plan_id: str,
    customer_notify: int = 1,
    start_at: int | None = None,
    expire_by: int | None = None,
) -> dict:
    """
    Create a Razorpay subscription.
    The subscription includes a trial period defined by the plan.
    The customer must complete mandate authorization via Razorpay Checkout.

    NOTE: Razorpay requires explicit recurring-payment authorization.
    Some payment methods require a ₹1 mandate registration — this is
    disclosed in the frontend checkout flow before the user proceeds.

    Returns the full Razorpay subscription object.
    """
    client = _get_client()
    import time

    payload = {
        "plan_id": plan_id,
        "total_count": 120,         # 10 years of monthly billing
        "quantity": 1,
        "customer_notify": customer_notify,
        "addons": [],
        "notes": {
            "service": "mediexplain-ai",
        },
    }
    if start_at is not None:
        payload["start_at"] = start_at
    if expire_by:
        payload["expire_by"] = expire_by

    try:
        subscription = client.subscription.create(payload)
        return subscription
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to create subscription: {e}",
        )


def fetch_subscription(gateway_subscription_id: str) -> dict:
    """Fetch current state of a subscription from Razorpay."""
    client = _get_client()
    try:
        return client.subscription.fetch(gateway_subscription_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch subscription: {e}",
        )


def cancel_subscription(gateway_subscription_id: str, cancel_at_cycle_end: bool = True) -> dict:
    """
    Cancel a Razorpay subscription.
    cancel_at_cycle_end=True means the subscription continues until the
    end of the current billing cycle (recommended — user gets what they paid for).
    """
    client = _get_client()
    try:
        return client.subscription.cancel(
            gateway_subscription_id,
            {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to cancel subscription: {e}",
        )


def verify_payment_signature(
    razorpay_subscription_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify the Razorpay payment signature after checkout completion.
    This must be called server-side — never trust the frontend's success callback alone.

    Returns True if signature is valid, False otherwise.
    """
    if not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service is not configured.",
        )
    msg = f"{razorpay_payment_id}|{razorpay_subscription_id}"
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature)

