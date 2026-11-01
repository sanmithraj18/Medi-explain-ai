"""
MediExplain AI — Auth Endpoint (profile management)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.core.dependencies import get_current_user
from app.db.supabase_client import get_supabase

router = APIRouter()


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None


@router.get("/me")
async def get_profile(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return authenticated user's profile."""
    result = (
        supabase.table("profiles")
        .select("*")
        .eq("id", current_user["id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return result.data


@router.patch("/me")
async def update_profile(
    body: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Update the current user's display name."""
    updates = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name.strip()[:100]

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    supabase.table("profiles").update(updates).eq("id", current_user["id"]).execute()
    return {"message": "Profile updated"}

