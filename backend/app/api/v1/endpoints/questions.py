"""
MediExplain AI — Doctor Questions Endpoint
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.core.dependencies import get_current_user
from app.db.supabase_client import get_supabase

router = APIRouter()


class UpdateQuestionStatus(BaseModel):
    discussion_status: str  # 'PENDING' | 'DISCUSSED'


def _verify_question_ownership(
    question_id: str, user_id: str, supabase: Client
) -> dict:
    """Verify the question belongs to this user via join through medical_reports."""
    result = (
        supabase.table("doctor_questions")
        .select("*, medical_reports!inner(user_id)")
        .eq("id", question_id)
        .eq("medical_reports.user_id", user_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return result.data


@router.get("/report/{report_id}")
async def get_questions_for_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get all doctor questions for a report (ownership verified)."""
    # Verify ownership
    report = (
        supabase.table("medical_reports")
        .select("id")
        .eq("id", report_id)
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    questions = (
        supabase.table("doctor_questions")
        .select("*")
        .eq("report_id", report_id)
        .order("question_order")
        .execute()
    )
    return {"questions": questions.data or []}


@router.patch("/{question_id}/status")
async def update_question_status(
    question_id: str,
    body: UpdateQuestionStatus,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Mark a question as discussed or reset to pending."""
    if body.discussion_status not in ("PENDING", "DISCUSSED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="discussion_status must be 'PENDING' or 'DISCUSSED'",
        )
    _verify_question_ownership(question_id, current_user["id"], supabase)
    supabase.table("doctor_questions").update(
        {"discussion_status": body.discussion_status}
    ).eq("id", question_id).execute()
    return {"message": "Status updated"}

