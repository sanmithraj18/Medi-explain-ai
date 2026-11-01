"""
MediExplain AI — FastAPI dependency injection.
Provides get_current_user and require_admin for all protected endpoints.
"""
from fastapi import Depends, Header, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase
from app.core.security import verify_supabase_token, extract_bearer_token


async def get_current_user(
    authorization: str | None = Header(default=None),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """
    FastAPI dependency: validates the Bearer token and returns the
    authenticated user. Raises HTTP 401 if the token is missing or invalid.
    """
    token = extract_bearer_token(authorization)
    user = await verify_supabase_token(token, supabase)
    return user


async def require_email_verified(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Raises HTTP 403 if the user has not verified their email."""
    if not current_user.get("email_confirmed"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return current_user


async def require_admin(
    current_user: dict = Depends(require_email_verified),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """
    Raises HTTP 403 if the authenticated user does not have admin privileges.
    Admin flag is read from the database — never from the JWT payload.
    """
    try:
        result = (
            supabase.table("profiles")
            .select("is_admin")
            .eq("id", current_user["id"])
            .single()
            .execute()
        )
        if not result.data or not result.data.get("is_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrator access required",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not verify admin status",
        )
    return current_user


async def require_active_subscription(
    current_user: dict = Depends(require_email_verified),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """
    Raises HTTP 402 if the user has no active trial or paid subscription.
    Access-control is enforced server-side — never trust the frontend.
    """
    from app.services.subscription.trial_service import evaluate_subscription_access

    try:
        result = (
            supabase.table("subscriptions")
            .select("subscription_status, trial_end_date")
            .eq("user_id", current_user["id"])
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No active subscription found",
            )

        sub = result.data
        can_access, canonical_status, _ = evaluate_subscription_access(sub)

        if can_access:
            return current_user

        # If trial expired past due date, update DB status asynchronously
        if canonical_status == "EXPIRED" and sub.get("subscription_status") == "TRIAL_ACTIVE":
            try:
                supabase.table("subscriptions").update(
                    {"subscription_status": "EXPIRED"}
                ).eq("user_id", current_user["id"]).execute()
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Free trial has expired. Please subscribe to continue.",
            )

        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Subscription status '{canonical_status}' does not allow access. "
                   "Please activate or renew your subscription.",
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not verify subscription status",
        )

