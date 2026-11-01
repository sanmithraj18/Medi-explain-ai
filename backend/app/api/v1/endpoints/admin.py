"""
MediExplain AI — Admin Dashboard Endpoint
Access restricted to users with is_admin=TRUE in the profiles table.
Revenue is calculated from VERIFIED payment records only.
"""
from fastapi import APIRouter, Depends
from supabase import Client

from app.core.dependencies import require_admin
from app.db.supabase_client import get_supabase

router = APIRouter()


@router.get("/stats")
async def get_admin_stats(
    _: dict = Depends(require_admin),
    supabase: Client = Depends(get_supabase),
):
    """
    Return aggregate platform statistics.
    Revenue is calculated from actual CAPTURED payments only.
    Medical report contents are never exposed here.
    """
    # User counts
    profiles = supabase.table("profiles").select("id", count="exact").execute()
    total_users = profiles.count or 0

    # Subscription breakdowns
    sub_counts = {}
    for stat_status in (
        "TRIAL_ACTIVE", "TRIAL_EXPIRED", "ACTIVE",
        "CANCELLED", "PAYMENT_FAILED", "HALTED"
    ):
        r = (
            supabase.table("subscriptions")
            .select("id", count="exact")
            .eq("subscription_status", stat_status)
            .execute()
        )
        sub_counts[stat_status.lower()] = r.count or 0

    # Payment statistics — from verified payment records only
    payments_captured = (
        supabase.table("payments")
        .select("amount", count="exact")
        .eq("payment_status", "CAPTURED")
        .execute()
    )
    payment_count = payments_captured.count or 0
    mrr_paise = sum(p["amount"] for p in (payments_captured.data or []))

    payments_failed = (
        supabase.table("payments")
        .select("id", count="exact")
        .eq("payment_status", "FAILED")
        .execute()
    )

    # Report counts
    reports_total = (
        supabase.table("medical_reports")
        .select("id", count="exact")
        .execute()
    )
    reports_completed = (
        supabase.table("medical_reports")
        .select("id", count="exact")
        .eq("processing_status", "COMPLETED")
        .execute()
    )

    return {
        "total_users": total_users,
        "subscriptions": sub_counts,
        "payments": {
            "successful_count": payment_count,
            "failed_count": payments_failed.count or 0,
            "total_revenue_paise": mrr_paise,
            "total_revenue_inr": mrr_paise / 100,
            "note": "Revenue calculated from verified CAPTURED payments only. Free trials are never counted as revenue.",
        },
        "reports": {
            "total": reports_total.count or 0,
            "completed": reports_completed.count or 0,
        },
    }

