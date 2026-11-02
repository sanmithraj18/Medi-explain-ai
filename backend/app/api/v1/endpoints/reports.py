"""
MediExplain AI — Reports Endpoint
Handles upload, status, listing and deletion of medical reports.

CREDENTIAL REQUIRED for upload to work:
  SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (backend/.env) — SECRET
  MAX_UPLOAD_SIZE_MB (backend/.env) — default 20
"""
import io
import re
import uuid
from datetime import datetime, timezone

import pymupdf as fitz
from PIL import Image
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request, status
from pydantic import BaseModel
from supabase import Client

from app.core.config import settings
from app.core.limiter import limiter
from app.core.dependencies import get_current_user, require_active_subscription
from app.db.supabase_client import get_supabase
from app.services.ocr.pdf_extractor import extract_text_from_pdf
from app.services.ocr.image_extractor import extract_text_from_image
from app.services.ocr.parameter_parser import parse_parameters
from app.services.ocr.pipeline import process_document_extraction

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}

ALLOWED_MAGIC_BYTES = {
    b"%PDF": "pdf",
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
}

MAX_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

DANGEROUS_PREFIXES = [
    b"MZ",            # Windows PE executable / DLL
    b"\x7fELF",       # Linux ELF binary
    b"<!DOCTYPE",     # Disguised HTML
    b"<html",         # Disguised HTML
    b"<?xml",         # Disguised XML / SVG
    b"#!",            # Shell script
]


def _sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent directory traversal or filesystem exploits."""
    # Strip null bytes and directory separators
    clean = re.sub(r"[\x00-\x1f/\\?%*:|\"<>]", "_", name).strip()
    # Prevent traversal
    clean = clean.replace("..", "_").strip("._ ")
    return clean or f"medical_report_{uuid.uuid4().hex[:8]}"


def _validate_file(file_bytes: bytes, content_type: str) -> str:
    """
    Perform deep validation of uploaded files:
    1. Size limit enforcement
    2. Rejection of 0-byte files
    3. Rejection of executables or scripts disguised as documents
    4. Magic-byte verification
    5. Structural integrity check via PyMuPDF (PDF) or Pillow (Images)
    """
    if not file_bytes or len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    if len(file_bytes) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit.",
        )

    # Security check: Disguised binary/script payload rejection
    for prefix in DANGEROUS_PREFIXES:
        if file_bytes.startswith(prefix):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security rejection: Executable or script payload detected.",
            )

    # Magic byte and structural integrity validation
    if file_bytes.startswith(b"%PDF"):
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if doc.is_encrypted:
                doc.close()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Encrypted or password-protected PDFs are not supported. Please upload an unlocked PDF.",
                )
            if doc.page_count == 0:
                doc.close()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The uploaded PDF contains no readable pages.",
                )
            doc.close()
            return "pdf"
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Corrupted or invalid PDF file: {str(e)[:100]}",
            )

    elif file_bytes.startswith(b"\xff\xd8\xff"):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            img.verify()
            return "jpg"
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corrupted or invalid JPEG image file.",
            )

    elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            img.verify()
            return "png"
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corrupted or invalid PNG image file.",
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported or unrecognized file format. Allowed types: PDF, JPG, PNG.",
        )


@router.post("/upload", status_code=201)
@limiter.limit("20/minute")
async def upload_report(
    request: Request,
    file: UploadFile = File(...),
    report_name: str = Form(default=None),
    current_user: dict = Depends(require_active_subscription),
    supabase: Client = Depends(get_supabase),
):
    """
    Upload a medical report file.
    Pipeline:
    1. Validate file type and size
    2. Store in private Supabase Storage under {user_id}/{report_id}/{filename}
    3. Create medical_reports record
    4. Run OCR extraction
    5. Store extracted parameters
    6. Return report ID for polling/redirect
    """
    user_id = current_user["id"]
    report_id = str(uuid.uuid4())

    # Read file
    file_bytes = await file.read()
    content_type = file.content_type or ""
    file_ext = _validate_file(file_bytes, content_type)

    raw_filename = file.filename or f"report.{file_ext}"
    safe_filename = _sanitize_filename(raw_filename)
    clean_name = report_name.strip() if report_name and report_name.strip() else raw_filename.rsplit(".", 1)[0]
    storage_path = f"{user_id}/{report_id}/{safe_filename}"

    # Upload to private Supabase Storage
    try:
        supabase.storage.from_("medical-reports").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "false"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File storage failed: {e}",
        )

    # Create report record
    report_record = {
        "id": report_id,
        "user_id": user_id,
        "report_name": clean_name,
        "file_path": storage_path,
        "file_type": file_ext,
        "file_size_bytes": len(file_bytes),
        "processing_status": "EXTRACTING",
        "upload_date": datetime.now(timezone.utc).isoformat(),
    }

    supabase.table("medical_reports").insert(report_record).execute()

    # Run document extraction pipeline
    parameters = []
    extraction_result = {}
    processing_status = "NEEDS_REVIEW"
    try:
        extraction_result = await process_document_extraction(
            file_bytes=file_bytes,
            file_ext=file_ext,
            content_type=content_type,
        )
        parameters = extraction_result.get("parameters", [])
        raw_text = extraction_result.get("raw_text", "")
        processing_status = extraction_result.get("processing_status", "NEEDS_REVIEW")

        # Update report name if Gemini vision identified a specific panel
        updated_report_name = clean_name
        if extraction_result.get("report_type") and any(
            g in clean_name.lower() for g in ["whatsapp", "camera_scan", "img_", "image", "photo", "report"]
        ):
            updated_report_name = f"{extraction_result['report_type']} ({clean_name})"

        # Update status and preserve original raw extracted text
        supabase.table("medical_reports").update(
            {
                "report_name": updated_report_name,
                "processing_status": processing_status,
                "raw_extracted_text": raw_text,
            }
        ).eq("id", report_id).execute()

        # Clean existing parameters and store freshly extracted parameters
        supabase.table("extracted_parameters").delete().eq("report_id", report_id).execute()
        if parameters:
            param_records = [
                {
                    "report_id": report_id,
                    "parameter_name": p["parameter_name"],
                    "observed_value": str(p["observed_value"]),
                    "unit": p.get("unit"),
                    "reference_min": p.get("reference_min"),
                    "reference_max": p.get("reference_max"),
                    "reference_text": p.get("reference_text"),
                    "laboratory_flag": p.get("laboratory_flag"),
                    "extraction_confidence": p.get("extraction_confidence", 0.9),
                    "needs_user_review": p.get("needs_user_review", False),
                    "user_confirmed": False,
                }
                for p in parameters
            ]
            supabase.table("extracted_parameters").insert(param_records).execute()

    except Exception as e:
        processing_status = "FAILED"
        supabase.table("medical_reports").update(
            {"processing_status": "FAILED", "processing_error": str(e)[:500]}
        ).eq("id", report_id).execute()

    return {
        "report_id": report_id,
        "report_name": updated_report_name if 'updated_report_name' in locals() else clean_name,
        "processing_status": processing_status,
        "parameters_found": len(parameters),
        "extraction_confidence": extraction_result.get("confidence", 0.0),
        "extraction_method": extraction_result.get("extraction_method", "ocr"),
        "needs_review": extraction_result.get("needs_review", True),
        "message": extraction_result.get(
            "message",
            "Report uploaded and processed successfully." if parameters else "No parameters could be extracted."
        ),
    }


@router.get("/")
async def list_reports(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """List all reports for the current user."""
    result = (
        supabase.table("medical_reports")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .execute()
    )
    return {"reports": result.data or []}


@router.get("/stats")
async def get_user_report_stats(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return dashboard summary metrics for the authenticated user."""
    reports_res = (
        supabase.table("medical_reports")
        .select("id, processing_status")
        .eq("user_id", current_user["id"])
        .execute()
    )
    reports = reports_res.data or []
    total = len(reports)
    completed = sum(1 for r in reports if r.get("processing_status") == "COMPLETED")
    needs_review = sum(1 for r in reports if r.get("processing_status") == "NEEDS_REVIEW")
    processing = sum(1 for r in reports if r.get("processing_status") in ("PENDING", "EXTRACTING", "ANALYZING"))

    return {
        "total_reports": total,
        "completed_explanations": completed,
        "needs_review": needs_review,
        "processing": processing,
    }


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get a single report (must belong to current user)."""
    result = (
        supabase.table("medical_reports")
        .select("*")
        .eq("id", report_id)
        .eq("user_id", current_user["id"])  # Ownership check
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return result.data


@router.get("/{report_id}/parameters")
async def get_report_parameters(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get extracted parameters for a report (ownership verified)."""
    # Verify ownership via join
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

    params = (
        supabase.table("extracted_parameters")
        .select("*")
        .eq("report_id", report_id)
        .order("created_at")
        .execute()
    )
    return {"parameters": params.data or []}


class ConfirmParameterRequest(BaseModel):
    observed_value: str | None = None
    unit: str | None = None


@router.patch("/{report_id}/parameters/{param_id}/confirm")
async def confirm_parameter(
    report_id: str,
    param_id: str,
    body: ConfirmParameterRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Allow patient to confirm or adjust an extracted lab parameter flagged for review.
    Enforces ownership of the parent report.
    """
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

    updates: dict = {"needs_user_review": False, "user_confirmed": True}
    if body.observed_value is not None:
        updates["observed_value"] = body.observed_value.strip()
    if body.unit is not None:
        updates["unit"] = body.unit.strip()

    supabase.table("extracted_parameters").update(updates).eq("id", param_id).eq("report_id", report_id).execute()
    return {"message": "Parameter confirmed successfully", "updates": updates}


@router.post("/{report_id}/re-extract")
@limiter.limit("10/minute")
async def re_extract_report(
    request: Request,
    report_id: str,
    current_user: dict = Depends(require_active_subscription),
    supabase: Client = Depends(get_supabase),
):
    """
    Re-extract laboratory parameters from an uploaded report using the complete AI Vision pipeline.
    Downloads the original report from private Supabase Storage, re-analyzes, and atomically updates parameters.
    """
    # 1. Verify report ownership
    report_res = (
        supabase.table("medical_reports")
        .select("*")
        .eq("id", report_id)
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not report_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    report_data = report_res.data
    file_path = report_data["file_path"]
    file_ext = report_data.get("file_type") or "jpg"

    # 2. Download original file bytes from Supabase storage
    try:
        file_bytes = supabase.storage.from_("medical-reports").download(file_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve original document from storage: {e}",
        )

    # 3. Mark as EXTRACTING
    supabase.table("medical_reports").update(
        {"processing_status": "EXTRACTING"}
    ).eq("id", report_id).execute()

    # 4. Re-run document extraction pipeline
    content_type = "application/pdf" if file_ext == "pdf" else "image/jpeg"
    try:
        extraction_result = await process_document_extraction(
            file_bytes=file_bytes,
            file_ext=file_ext,
            content_type=content_type,
        )
        parameters = extraction_result.get("parameters", [])
        raw_text = extraction_result.get("raw_text", "")
        processing_status = extraction_result.get("processing_status", "NEEDS_REVIEW")

        # 5. Atomically replace extracted parameters
        supabase.table("extracted_parameters").delete().eq("report_id", report_id).execute()
        if parameters:
            param_records = [
                {
                    "report_id": report_id,
                    "parameter_name": p["parameter_name"],
                    "observed_value": str(p["observed_value"]),
                    "unit": p.get("unit"),
                    "reference_min": p.get("reference_min"),
                    "reference_max": p.get("reference_max"),
                    "reference_text": p.get("reference_text"),
                    "laboratory_flag": p.get("laboratory_flag"),
                    "extraction_confidence": p.get("extraction_confidence", 0.9),
                    "needs_user_review": p.get("needs_user_review", False),
                    "user_confirmed": False,
                }
                for p in parameters
            ]
            supabase.table("extracted_parameters").insert(param_records).execute()

        # 6. Update report record
        updates: dict[str, Any] = {
            "processing_status": processing_status,
            "raw_extracted_text": raw_text,
            "processing_error": None,
        }
        if extraction_result.get("report_type"):
            updates["report_name"] = f"{extraction_result['report_type']} ({report_data.get('report_name', 'Report')})"

        supabase.table("medical_reports").update(updates).eq("id", report_id).execute()

        return {
            "report_id": report_id,
            "processing_status": processing_status,
            "parameters_found": len(parameters),
            "extraction_method": extraction_result.get("extraction_method"),
            "confidence": extraction_result.get("confidence"),
            "needs_review": extraction_result.get("needs_review"),
            "message": extraction_result.get("message"),
            "parameters": parameters,
        }

    except Exception as e:
        supabase.table("medical_reports").update(
            {"processing_status": "FAILED", "processing_error": str(e)[:500]}
        ).eq("id", report_id).execute()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Re-extraction failed: {e}",
        )



@router.get("/{report_id}/raw-text")
async def get_report_raw_text(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Retrieve original preserved raw text from OCR/PyMuPDF for document verification.
    """
    report = (
        supabase.table("medical_reports")
        .select("raw_extracted_text, report_name")
        .eq("id", report_id)
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return {
        "report_id": report_id,
        "report_name": report.data.get("report_name"),
        "raw_extracted_text": report.data.get("raw_extracted_text") or "",
    }


@router.get("/{report_id}/download-url")
async def get_download_url(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Generate a short-lived signed URL for the report file.
    URL expires in 60 minutes. Never expose permanent public links.
    """
    report = (
        supabase.table("medical_reports")
        .select("file_path")
        .eq("id", report_id)
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    try:
        signed = supabase.storage.from_("medical-reports").create_signed_url(
            report.data["file_path"],
            expires_in=3600,  # 60 minutes
        )
        url = signed.get("signedURL") or signed.get("signedUrl") if isinstance(signed, dict) else str(signed)
        return {"signed_url": url, "expires_in": 3600}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate download URL: {e}",
        )


@router.delete("/{report_id}", status_code=200)
async def delete_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Delete a report and its associated file from storage."""
    report = (
        supabase.table("medical_reports")
        .select("file_path")
        .eq("id", report_id)
        .eq("user_id", current_user["id"])
        .single()
        .execute()
    )
    if not report.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    # Delete from Storage
    try:
        supabase.storage.from_("medical-reports").remove([report.data["file_path"]])
    except Exception:
        pass  # Log but don't fail — DB record should still be deleted

    # Delete DB record (cascades to parameters, analyses, questions)
    supabase.table("medical_reports").delete().eq("id", report_id).execute()

    return {"message": "Report deleted successfully"}

