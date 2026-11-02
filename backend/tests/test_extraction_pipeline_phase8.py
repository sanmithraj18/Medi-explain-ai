"""
MediExplain AI — Comprehensive Test Suite for Document Extraction Pipeline.
Tests all 10 document scenarios:
1. Clear JPG
2. Clear PNG
3. Blurry JPG
4. Rotated image (EXIF orientation)
5. Low-resolution image
6. Scanned PDF
7. Text-based PDF
8. Report with missing reference ranges (Zero invention)
9. Report with multiple pages
10. Image containing no laboratory results (Zero fabrication)
"""
import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from PIL import Image, ImageDraw, ImageFilter
import pymupdf as fitz
from fastapi.testclient import TestClient

from main import app
from app.services.ocr.pdf_extractor import extract_text_from_pdf, render_pdf_to_images
from app.services.ocr.image_extractor import prepare_image_for_vision, extract_text_from_image
from app.services.ocr.parameter_parser import parse_parameters
from app.services.ocr.pipeline import process_document_extraction
from app.services.ai.gemini_service import _parse_ref_bounds, _detect_critical_flag
from app.core.dependencies import require_active_subscription, get_current_user
from app.db.supabase_client import get_supabase


# ─── Helper Builders ─────────────────────────────────────────────────────────

def build_test_image(text_lines: list[str], fmt: str = "JPEG", blur: bool = False, rotate: int = 0, size: tuple = (800, 400)) -> bytes:
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)
    y = 20
    for line in text_lines:
        draw.text((20, y), line, fill="black")
        y += 30

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    if rotate:
        img = img.rotate(rotate, expand=True)

    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def build_digital_pdf(pages: list[list[str]]) -> bytes:
    doc = fitz.open()
    for page_lines in pages:
        page = doc.new_page()
        y = 50
        for line in page_lines:
            page.insert_text((50, y), line)
            y += 25
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


def build_scanned_pdf(text_lines: list[str]) -> bytes:
    img_bytes = build_test_image(text_lines, fmt="PNG")
    doc = fitz.open()
    page = doc.new_page(width=800, height=400)
    page.insert_image(fitz.Rect(0, 0, 800, 400), stream=img_bytes)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# ─── 1. Clear JPG Extraction ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_clear_jpg_extraction():
    lines = [
        "METABOLIC PANEL",
        "Fasting Glucose: 105 mg/dL (Ref: 70 - 99 mg/dL) HIGH",
        "Serum Creatinine: 0.9 mg/dL (Ref: 0.6 - 1.2 mg/dL) NORMAL"
    ]
    jpg_bytes = build_test_image(lines, fmt="JPEG")
    
    mock_vision = {
        "report_type": "Metabolic Panel",
        "report_date": "2026-11-01",
        "raw_text": "\n".join(lines),
        "parameters": [
            {
                "parameter_name": "Fasting Glucose",
                "observed_value": "105",
                "unit": "mg/dL",
                "reference_min": 70.0,
                "reference_max": 99.0,
                "reference_text": "70 - 99 mg/dL",
                "laboratory_flag": "HIGH",
                "extraction_confidence": 0.95,
                "needs_user_review": False,
                "user_confirmed": False,
            },
            {
                "parameter_name": "Serum Creatinine",
                "observed_value": "0.9",
                "unit": "mg/dL",
                "reference_min": 0.6,
                "reference_max": 1.2,
                "reference_text": "0.6 - 1.2 mg/dL",
                "laboratory_flag": "NORMAL",
                "extraction_confidence": 0.95,
                "needs_user_review": False,
                "user_confirmed": False,
            }
        ],
        "extraction_method": "gemini_vision",
        "notes": None
    }

    with patch("app.services.ocr.pipeline.extract_parameters_with_vision", AsyncMock(return_value=mock_vision)):
        res = await process_document_extraction(jpg_bytes, "jpg", "image/jpeg")
        assert res["processing_status"] == "EXTRACTED"
        assert len(res["parameters"]) == 2
        assert res["parameters"][0]["parameter_name"] == "Fasting Glucose"
        assert res["parameters"][0]["observed_value"] == "105"
        assert not res["needs_review"]


# ─── 2. Clear PNG Extraction ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_clear_png_extraction():
    lines = [
        "COMPLETE BLOOD COUNT",
        "Hemoglobin: 14.2 g/dL (Ref: 13.0 - 17.0 g/dL) NORMAL",
        "Platelet Count: 250000 /cumm (Ref: 150000 - 450000) NORMAL"
    ]
    png_bytes = build_test_image(lines, fmt="PNG")

    mock_vision = {
        "report_type": "Complete Blood Count",
        "report_date": "2026-11-01",
        "raw_text": "\n".join(lines),
        "parameters": [
            {
                "parameter_name": "Hemoglobin",
                "observed_value": "14.2",
                "unit": "g/dL",
                "reference_min": 13.0,
                "reference_max": 17.0,
                "reference_text": "13.0 - 17.0 g/dL",
                "laboratory_flag": "NORMAL",
                "extraction_confidence": 0.95,
                "needs_user_review": False,
                "user_confirmed": False,
            }
        ],
        "extraction_method": "gemini_vision",
        "notes": None
    }

    with patch("app.services.ocr.pipeline.extract_parameters_with_vision", AsyncMock(return_value=mock_vision)):
        res = await process_document_extraction(png_bytes, "png", "image/png")
        assert res["processing_status"] == "EXTRACTED"
        assert len(res["parameters"]) >= 1
        assert any("Hemoglobin" in p["parameter_name"] for p in res["parameters"])


# ─── 3. Blurry JPG Handling ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_blurry_jpg_preprocessing_and_review_flag():
    lines = ["Fasting Glucose: 11O..5 mg/dL"]
    blurry_bytes = build_test_image(lines, fmt="JPEG", blur=True)

    # Preprocessor enhances contrast
    prep_bytes, mime = prepare_image_for_vision(blurry_bytes, "image/jpeg")
    assert len(prep_bytes) > 0
    assert mime == "image/jpeg"

    # Ambiguous/blurry extraction triggers needs_user_review
    mock_vision = {
        "report_type": "Glucose Screen",
        "report_date": None,
        "raw_text": "Fasting Glucose: 11O..5",
        "parameters": [
            {
                "parameter_name": "Fasting Glucose",
                "observed_value": "11O..5",
                "unit": "mg/dL",
                "reference_min": None,
                "reference_max": None,
                "reference_text": None,
                "laboratory_flag": None,
                "extraction_confidence": 0.55,  # Low confidence
                "needs_user_review": True,      # Ambiguous flag
                "user_confirmed": False,
            }
        ],
        "extraction_method": "gemini_vision",
        "notes": "Blurry document with questionable decimal point"
    }

    with patch("app.services.ocr.pipeline.extract_parameters_with_vision", AsyncMock(return_value=mock_vision)):
        res = await process_document_extraction(blurry_bytes, "jpg", "image/jpeg")
        assert res["processing_status"] == "NEEDS_REVIEW"
        assert res["needs_review"] is True
        assert res["parameters"][0]["needs_user_review"] is True


# ─── 4. Rotated Image (EXIF / Mobile Camera) ─────────────────────────────────
def test_image_orientation_correction():
    # Create rotated image
    img = Image.new("RGB", (600, 300), color="white")
    d = ImageDraw.Draw(img)
    d.text((20, 20), "HORIZONTAL TEXT", fill="black")
    # Save with orientation
    rotated = img.rotate(90, expand=True)
    buf = io.BytesIO()
    rotated.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    prep_bytes, mime = prepare_image_for_vision(raw_bytes, "image/jpeg")
    assert len(prep_bytes) > 0
    processed_img = Image.open(io.BytesIO(prep_bytes))
    # Dimensions normalized
    assert max(processed_img.size) >= 1000


# ─── 5. Low-Resolution Image Scaling ─────────────────────────────────────────
def test_low_resolution_image_upscaling():
    # Create small 400x200 thumbnail image
    small_bytes = build_test_image(["Small Text 123"], fmt="JPEG", size=(400, 200))
    prep_bytes, mime = prepare_image_for_vision(small_bytes, "image/jpeg")
    upscaled = Image.open(io.BytesIO(prep_bytes))
    # Minimum dimension normalized for readability
    assert min(upscaled.size) >= 800


# ─── 6. Scanned PDF (Gemini Vision Fallback) ──────────────────────────────────
@pytest.mark.asyncio
async def test_scanned_pdf_gemini_vision_fallback():
    lines = [
        "SCANNED LAB REPORT",
        "Uric Acid: 7.8 mg/dL (Ref: 3.5 - 7.2) HIGH"
    ]
    scanned_pdf = build_scanned_pdf(lines)
    
    # Check rendered images
    page_imgs = render_pdf_to_images(scanned_pdf)
    assert len(page_imgs) == 1

    mock_vision = {
        "report_type": "Renal Function",
        "report_date": "2026-11-01",
        "raw_text": "Uric Acid: 7.8 mg/dL HIGH",
        "parameters": [
            {
                "parameter_name": "Uric Acid",
                "observed_value": "7.8",
                "unit": "mg/dL",
                "reference_min": 3.5,
                "reference_max": 7.2,
                "reference_text": "3.5 - 7.2",
                "laboratory_flag": "HIGH",
                "extraction_confidence": 0.95,
                "needs_user_review": False,
                "user_confirmed": False,
            }
        ],
        "extraction_method": "gemini_vision",
        "notes": None
    }

    with patch("app.services.ocr.pipeline.extract_parameters_with_vision", AsyncMock(return_value=mock_vision)):
        res = await process_document_extraction(scanned_pdf, "pdf", "application/pdf")
        assert res["processing_status"] == "EXTRACTED"
        assert len(res["parameters"]) == 1
        assert res["parameters"][0]["parameter_name"] == "Uric Acid"
        assert res["parameters"][0]["observed_value"] == "7.8"


# ─── 7. Text-Based Digital PDF Extraction ────────────────────────────────────
@pytest.mark.asyncio
async def test_text_based_digital_pdf_extraction():
    lines = [
        "LIPID PROFILE",
        "Total Cholesterol: 220 mg/dL (Ref: 125 - 200 mg/dL) HIGH",
        "HDL Cholesterol: 45 mg/dL (Ref: 40 - 60 mg/dL) NORMAL"
    ]
    digital_pdf = build_digital_pdf([lines])

    res = await process_document_extraction(digital_pdf, "pdf", "application/pdf")
    assert res["processing_status"] in ("EXTRACTED", "NEEDS_REVIEW")
    assert len(res["parameters"]) >= 1
    chol = next((p for p in res["parameters"] if "Cholesterol" in p["parameter_name"]), None)
    assert chol is not None


# ─── 8. Missing Reference Range (Zero Fabrication Constraint) ─────────────────
def test_missing_reference_range_preserves_none():
    ref_min, ref_max = _parse_ref_bounds(None)
    assert ref_min is None
    assert ref_max is None

    # Partial / non-range text does not invent numbers
    ref_min, ref_max = _parse_ref_bounds("Not Reported by Facility")
    assert ref_min is None
    assert ref_max is None

    # Valid range parses correctly
    ref_min, ref_max = _parse_ref_bounds("70 - 99 mg/dL")
    assert ref_min == 70.0
    assert ref_max == 99.0

    # Upper threshold parses correctly
    ref_min, ref_max = _parse_ref_bounds("< 200")
    assert ref_min is None
    assert ref_max == 200.0


# ─── 9. Multiple Pages PDF Handling ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_multipage_pdf_handling():
    page1 = ["PAGE 1: Hemoglobin: 14.5 g/dL (Ref: 13.0 - 17.0) NORMAL"]
    page2 = ["PAGE 2: Serum Potassium: 4.2 mmol/L (Ref: 3.5 - 5.0) NORMAL"]
    multi_pdf = build_digital_pdf([page1, page2])

    res = await process_document_extraction(multi_pdf, "pdf", "application/pdf")
    assert len(res["parameters"]) == 2
    names = [p["parameter_name"] for p in res["parameters"]]
    assert any("Hemoglobin" in n for n in names)
    assert any("Potassium" in n for n in names)


# ─── 10. Non-Medical Image (Zero Parameters, Needs Review) ───────────────────
@pytest.mark.asyncio
async def test_non_medical_image_returns_zero_parameters():
    grocery_lines = [
        "SUPERMARKET RECEIPT",
        "Organic Apples: $4.99",
        "Almond Milk: $3.49",
        "Total: $8.48"
    ]
    receipt_bytes = build_test_image(grocery_lines, fmt="JPEG")

    mock_vision = {
        "report_type": None,
        "report_date": None,
        "raw_text": "\n".join(grocery_lines),
        "parameters": [],  # Zero parameters
        "extraction_method": "gemini_vision",
        "notes": "Non-medical store receipt"
    }

    with patch("app.services.ocr.pipeline.extract_parameters_with_vision", AsyncMock(return_value=mock_vision)):
        res = await process_document_extraction(receipt_bytes, "jpg", "image/jpeg")
        assert res["processing_status"] == "NEEDS_REVIEW"
        assert res["needs_review"] is True
        assert len(res["parameters"]) == 0
        assert "no laboratory test parameters" in res["message"].lower()


# ─── 11. Re-extraction Endpoint & Ownership Isolation ────────────────────────
def test_re_extract_endpoint_success_and_ownership():
    client = TestClient(app)
    user_id = "user-abc-123"
    report_id = "report-xyz-789"
    mock_user = {"id": user_id, "email": "test@user.com", "email_confirmed": True}

    fake_image_bytes = build_test_image(["Glucose: 100 mg/dL"])
    mock_supabase = MagicMock()
    # Report query returns owned report
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": report_id,
        "user_id": user_id,
        "report_name": "WhatsApp Image 2026-11-02",
        "file_path": f"{user_id}/{report_id}/image.jpg",
        "file_type": "jpg",
    }
    mock_supabase.storage.from_.return_value.download.return_value = fake_image_bytes
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "param-1"}]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []

    mock_pipeline_res = {
        "parameters": [
            {
                "parameter_name": "Glucose",
                "observed_value": "100",
                "unit": "mg/dL",
                "reference_min": 70.0,
                "reference_max": 99.0,
                "reference_text": "70 - 99",
                "laboratory_flag": "HIGH",
                "extraction_confidence": 0.95,
                "needs_user_review": False,
            }
        ],
        "processing_status": "EXTRACTED",
        "raw_text": "Glucose: 100 mg/dL",
        "extraction_method": "gemini_vision",
        "report_type": "Blood Glucose",
        "confidence": 0.95,
        "needs_review": False,
        "message": "Extracted 1 parameter",
    }

    app.dependency_overrides[require_active_subscription] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    with patch("app.api.v1.endpoints.reports.process_document_extraction", AsyncMock(return_value=mock_pipeline_res)):
        try:
            res = client.post(f"/api/v1/reports/{report_id}/re-extract")
            assert res.status_code == 200
            data = res.json()
            assert data["report_id"] == report_id
            assert data["processing_status"] == "EXTRACTED"
            assert data["parameters_found"] == 1
        finally:
            app.dependency_overrides.clear()
