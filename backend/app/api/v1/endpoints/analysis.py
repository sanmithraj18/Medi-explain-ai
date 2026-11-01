"""
MediExplain AI — Analysis Endpoint
Triggers Gemini-powered medical report explanations and stores structured results.

CREDENTIAL REQUIRED:
  AI_API_KEY — Google Gemini API key (backend/.env) — SECRET
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from supabase import Client

from app.core.limiter import limiter
from app.core.dependencies import get_current_user, require_active_subscription
from app.db.supabase_client import get_supabase
from app.services.ai.gemini_service import (
    generate_overall_summary,
    generate_parameter_explanation,
)
from app.schemas.analysis import AnalysisTriggerResponse
from app.core.config import settings

router = APIRouter()


@router.post("/{report_id}/trigger", response_model=AnalysisTriggerResponse)
@limiter.limit("15/minute")
async def trigger_analysis(
    request: Request,
    report_id: str,
    current_user: dict = Depends(require_active_subscription),
    supabase: Client = Depends(get_supabase),
):
    """
    Trigger AI analysis for an extracted medical report.
    Enforces medical safety rules:
    - Never invents values, units, or reference ranges.
    - Does NOT generate explanations for unconfirmed parameters requiring user review.
    - Employs strict server-side ownership checks.
    """
    # 1. Verify report ownership
    report = (
        supabase.table("medical_reports")
        .select("id, processing_status, report_name, user_id")
        .eq("id", report_id)
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    report_data = report.data
    if report_data["processing_status"] not in ("EXTRACTED", "NEEDS_REVIEW", "COMPLETED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is not ready for analysis (current status: {report_data['processing_status']}). "
                   "Please wait for OCR extraction to complete.",
        )

    # 2. Fetch extracted parameters for this report
    params_result = (
        supabase.table("extracted_parameters")
        .select("*")
        .eq("report_id", report_id)
        .execute()
    )
    parameters = params_result.data or []

    if not parameters:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No parameters found for this report. The report may require manual review or re-upload.",
        )

    # 3. Segregate confirmed parameters vs unconfirmed parameters requiring review
    confirmed_params = [
        p for p in parameters
        if not (p.get("needs_user_review") and not p.get("user_confirmed"))
    ]
    unconfirmed_params = [
        p for p in parameters
        if p.get("needs_user_review") and not p.get("user_confirmed")
    ]

    if not confirmed_params and unconfirmed_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All extracted parameters are flagged for verification. Please verify or adjust ambiguous values on the report page before generating AI explanations.",
        )

    # 4. Mark report as ANALYZING
    supabase.table("medical_reports").update(
        {"processing_status": "ANALYZING"}
    ).eq("id", report_id).execute()

    try:
        # 5. Generate overall clinical summary on confirmed parameters only
        overall_summary = await generate_overall_summary(confirmed_params)

        # 6. Generate detailed parameter explanations
        detailed_explanation = {}

        # A. Process confirmed parameters via Gemini
        for param in confirmed_params:
            try:
                explanation = await generate_parameter_explanation(param)
                detailed_explanation[param["parameter_name"]] = explanation
            except Exception as e:
                detailed_explanation[param["parameter_name"]] = {
                    "parameter_name": param["parameter_name"],
                    "observed_value": str(param.get("observed_value", "")),
                    "unit": param.get("unit"),
                    "reference_range": param.get("reference_text"),
                    "classification": "UNKNOWN",
                    "what_it_measures": "Information temporarily unavailable.",
                    "simple_explanation": "An educational explanation could not be generated at this time.",
                    "contextual_limitations": "Individual parameter explanation failed.",
                    "when_to_seek_attention": "Please discuss this parameter directly with your doctor.",
                    "doctor_questions": [],
                    "disclaimer": "Informational purpose only.",
                }

        # B. For unconfirmed parameters: add safety placeholder without calling AI
        for param in unconfirmed_params:
            detailed_explanation[param["parameter_name"]] = {
                "parameter_name": param["parameter_name"],
                "observed_value": str(param.get("observed_value", "")),
                "unit": param.get("unit"),
                "reference_range": param.get("reference_text"),
                "classification": "UNCONFIRMED_OCR_VALUE",
                "what_it_measures": "Unverified OCR extraction",
                "simple_explanation": "This value was flagged for user confirmation due to ambiguous characters in the document scan. Please confirm or adjust the value on the report page to generate an explanation.",
                "contextual_limitations": "Unconfirmed extraction",
                "when_to_seek_attention": "Please verify this value against your physical report.",
                "doctor_questions": [],
                "needs_user_review": True,
                "disclaimer": "This value has not yet been confirmed by the patient.",
            }

        # 7. Extract questions
        questions = overall_summary.get("doctor_discussion_questions", [])

        # 8. Clear previous analysis and questions if re-running
        supabase.table("report_analyses").delete().eq("report_id", report_id).execute()
        supabase.table("doctor_questions").delete().eq("report_id", report_id).execute()

        # 9. Store analysis in database
        analysis_record = {
            "report_id": report_id,
            "overall_summary": overall_summary,
            "detailed_explanation": detailed_explanation,
            "limitations": overall_summary.get("key_limitations", []),
            "ai_model": settings.AI_MODEL,
            "prompt_version": "1.0",
        }
        analysis_result = supabase.table("report_analyses").insert(analysis_record).execute()

        # 10. Store doctor questions
        if questions:
            question_records = [
                {
                    "report_id": report_id,
                    "question": q,
                    "question_order": i,
                    "discussion_status": "PENDING",
                }
                for i, q in enumerate(questions)
                if isinstance(q, str) and q.strip()
            ]
            if question_records:
                supabase.table("doctor_questions").insert(question_records).execute()

        # 11. Mark report as COMPLETED
        supabase.table("medical_reports").update(
            {"processing_status": "COMPLETED"}
        ).eq("id", report_id).execute()

        return AnalysisTriggerResponse(
            analysis_id=analysis_result.data[0]["id"] if analysis_result.data else None,
            report_id=report_id,
            parameters_analyzed=len(confirmed_params),
            unconfirmed_parameters_skipped=len(unconfirmed_params),
            questions_generated=len(questions),
            message="Educational report explanation generated successfully.",
            disclaimer=(
                "This explanation is for educational purposes only and does not constitute medical advice, "
                "diagnosis, or treatment recommendations. Always discuss findings with a qualified healthcare professional."
            ),
        )

    except HTTPException:
        supabase.table("medical_reports").update(
            {"processing_status": "FAILED"}
        ).eq("id", report_id).execute()
        raise
    except Exception as e:
        supabase.table("medical_reports").update(
            {"processing_status": "FAILED", "processing_error": str(e)[:500]}
        ).eq("id", report_id).execute()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI analysis failed: {str(e)[:120]}",
        )


@router.get("/{report_id}")
async def get_analysis(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Fetch stored AI analysis for a report (strictly ownership verified)."""
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

    analysis = (
        supabase.table("report_analyses")
        .select("*")
        .eq("report_id", report_id)
        .single()
        .execute()
    )
    if not analysis.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found. Use POST /analysis/{report_id}/trigger to generate an explanation.",
        )
    return analysis.data
