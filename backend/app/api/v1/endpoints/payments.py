"""
MediExplain AI — Payments Endpoint (history only)
Actual payment processing is handled by Razorpay + webhooks.
"""
from fastapi import APIRouter, Depends
from supabase import Client

from app.core.dependencies import get_current_user
from app.db.supabase_client import get_supabase

router = APIRouter()


@router.get("/history")
async def get_payment_history(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return verified payment records for the current user."""
    result = (
        supabase.table("payments")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .execute()
    )
    return {"payments": result.data or []}

