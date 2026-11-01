"""
Comprehensive test suite for Phase 3: Medical Document OCR & Parameter Extraction.
Verifies all 15 Phase 3 requirements:
- Digital PDF extraction via PyMuPDF
- Scanned PDF fallback via Tesseract OCR
- Multi-page document handling
- Clear and blurry image extraction with preprocessing
- Missing reference range & missing unit preservation (no invention)
- Ambiguous number detection (preservation + review flag)
- Potentially critical findings detection
- Database parameter confirmation and user ownership
- Raw extracted text preservation
"""
import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter
import pymupdf as fitz

from main import app
from app.services.ocr.pdf_extractor import extract_text_from_pdf
from app.services.ocr.image_extractor import extract_text_from_image
from app.services.ocr.parameter_parser import parse_parameters
from app.core.dependencies import get_current_user
from app.db.supabase_client import get_supabase


# ─── Helper: Create Digital Multi-page PDF ────────────────────────────
def create_digital_pdf(pages_text: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((50, 72), text)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# ─── Helper: Create Scanned-like PDF (Image only on page) ─────────────
def create_scanned_pdf(text: str) -> bytes:
    # Render text onto PIL image first
    img = Image.new("RGB", (1000, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 50), text, fill="black")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=600, height=300)
    # Insert image without any digital text stream
    rect = fitz.Rect(0, 0, 600, 300)
    page.insert_image(rect, stream=img_bytes.getvalue())
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# ─── 1. Digital PDF Extraction ────────────────────────────────────────
def test_digital_pdf_extraction():
    content = """
    COMPREHENSIVE METABOLIC PANEL
    Glucose          92.0  mg/dL   70.0 - 99.0     N
    Blood Urea       24.0  mg/dL   15.0 - 40.0     N
    Serum Creatinine 0.95  mg/dL   0.60 - 1.20     N
    """
    pdf_bytes = create_digital_pdf([content])
    res = extract_text_from_pdf(pdf_bytes)

    assert res["method"] == "native"
    assert res["pages"] == 1
    assert res["confidence"] >= 0.90
    assert not res["needs_review"]
    assert "Glucose" in res["text"]

    params = parse_parameters(res["text"])
    assert len(params) == 3
    glu = next(p for p in params if "Glucose" in p["parameter_name"])
    assert glu["observed_value"] == "92.0"
    assert glu["unit"] == "mg/dL"
    assert glu["reference_min"] == 70.0
    assert glu["reference_max"] == 99.0
    assert glu["laboratory_flag"] == "N"


# ─── 2. Multi-page PDF Extraction ─────────────────────────────────────
def test_multipage_pdf_extraction():
    page1 = """
    COMPLETE BLOOD COUNT - PAGE 1
    Haemoglobin   14.5  g/dL   13.0 - 17.0   N
    Packed Cell Vol 42.0 %     40.0 - 50.0   N
    """
    page2 = """
    COMPLETE BLOOD COUNT - PAGE 2
    Total Leucocytes 6800 /cumm  4000 - 11000  N
    Platelet Count   240000 /cumm 150000 - 450000 N
    """
    pdf_bytes = create_digital_pdf([page1, page2])
    res = extract_text_from_pdf(pdf_bytes)

    assert res["pages"] == 2
    assert "Haemoglobin" in res["text"]
    assert "Platelet Count" in res["text"]

    params = parse_parameters(res["text"])
    assert len(params) == 4
    names = [p["parameter_name"] for p in params]
    assert any("Haemoglobin" in n for n in names)
    assert any("Platelet Count" in n for n in names)


# ─── 3. Scanned PDF Fallback via Tesseract ────────────────────────────
def test_scanned_pdf_fallback():
    scanned_text = "Platelet Count 210000 /cumm 150000 - 450000"
    pdf_bytes = create_scanned_pdf(scanned_text)
    res = extract_text_from_pdf(pdf_bytes)

    # Scanned PDF without native text triggers OCR
    assert res["method"] in ("ocr", "mixed")
    assert res["pages"] == 1
    assert "Platelet" in res["text"] or "210000" in res["text"]


# ─── 4. Clear Image Extraction ────────────────────────────────────────
def test_clear_image_extraction():
    img = Image.new("RGB", (1200, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 50), "Serum Bilirubin Total 0.8 mg/dL 0.2 - 1.2", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    res = extract_text_from_image(buf.getvalue(), "image/png")
    assert res["method"] == "ocr"
    assert "Bilirubin" in res["text"] or "0.8" in res["text"]


# ─── 5. Blurry Image Preprocessing ────────────────────────────────────
def test_blurry_image_preprocessing():
    img = Image.new("RGB", (1200, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 50), "Serum Uric Acid 5.5 mg/dL 3.5 - 7.2", fill="black")
    # Apply blur
    blurred = img.filter(ImageFilter.GaussianBlur(radius=1.0))
    buf = io.BytesIO()
    blurred.save(buf, format="JPEG")

    # Image extractor runs unsharp masking and contrast stretching
    res = extract_text_from_image(buf.getvalue(), "image/jpeg")
    assert res["method"] == "ocr"
    assert len(res["text"]) > 0


# ─── 6. Missing Reference Range (No Invention) ─────────────────────────
def test_missing_reference_range_not_invented():
    line = "Random Lab Observation 55.4 U/L"
    params = parse_parameters(line)
    assert len(params) == 1
    p = params[0]
    assert p["observed_value"] == "55.4"
    assert p["unit"] == "U/L"
    assert p["reference_min"] is None
    assert p["reference_max"] is None
    assert p["reference_text"] is None


# ─── 7. Missing Unit (No Invention) ───────────────────────────────────
def test_missing_unit_not_invented():
    line = "Anion Gap 12.0 8.0 - 16.0"
    params = parse_parameters(line)
    assert len(params) == 1
    p = params[0]
    assert p["observed_value"] == "12.0"
    # Unit should be None (not invented)
    assert p["unit"] is None
    assert p["reference_min"] == 8.0
    assert p["reference_max"] == 16.0


# ─── 8. Ambiguous Numbers Detection & User Review Flag ────────────────
def test_ambiguous_numbers_flagged_for_review():
    # Number with OCR artifact letter 'O' and double dot
    text = "Serum Creatinine 1O..2 mg/dL 0.6 - 1.2"
    params = parse_parameters(text)
    assert len(params) >= 1
    param = params[0]
    # Value preserved as original string
    assert "1O" in param["observed_value"] or ".." in param["observed_value"]
    # Flagged for user review
    assert param["needs_user_review"] is True
    assert param["extraction_confidence"] <= 0.60


# ─── 9. Critical Value Detection (Safety Guideline) ───────────────────
def test_critical_value_detection():
    # Critically low potassium < 2.8 mmol/L
    line = "Serum Potassium 2.4 mmol/L 3.5 - 5.1 L"
    params = parse_parameters(line)
    assert len(params) == 1
    p = params[0]
    assert p["laboratory_flag"] == "CRITICAL"
    assert p["safety_alert"] is not None
    assert "Critical physiological value" in p["safety_alert"]


# ─── 10. Raw Text Preservation Endpoint ───────────────────────────────
def test_get_raw_text_endpoint():
    client = TestClient(app)
    user_id = "user-123"
    report_id = "rep-999"
    mock_user = {"id": user_id, "email": "test@test.com", "email_confirmed": True}

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "raw_extracted_text": "Haemoglobin 14.2 g/dL 13-17",
        "report_name": "CBC Test",
    }

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        res = client.get(f"/api/v1/reports/{report_id}/raw-text")
        assert res.status_code == 200
        data = res.json()
        assert "raw_extracted_text" in data
        assert "Haemoglobin 14.2" in data["raw_extracted_text"]
    finally:
        app.dependency_overrides.clear()


# ─── 11. Parameter Confirmation Endpoint & Ownership ─────────────────
def test_confirm_parameter_endpoint():
    client = TestClient(app)
    user_id = "user-123"
    report_id = "rep-999"
    param_id = "param-111"
    mock_user = {"id": user_id, "email": "test@test.com", "email_confirmed": True}

    mock_supabase = MagicMock()
    # Mock report ownership query
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": report_id
    }
    # Mock parameter update
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": param_id}]

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        res = client.patch(
            f"/api/v1/reports/{report_id}/parameters/{param_id}/confirm",
            json={"observed_value": "14.2", "unit": "g/dL"},
        )
        assert res.status_code == 200
        assert res.json()["message"] == "Parameter confirmed successfully"
    finally:
        app.dependency_overrides.clear()

