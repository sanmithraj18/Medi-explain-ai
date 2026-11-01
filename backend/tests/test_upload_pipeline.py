"""
Comprehensive unit and integration tests for MediExplain AI Phase 2:
Medical Document Upload Pipeline, Deep File Validation, Security Guardrails,
and Storage Ownership Isolation.
"""
import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
from PIL import Image

from main import app
from app.api.v1.endpoints.reports import _validate_file, _sanitize_filename
from app.core.dependencies import get_current_user, require_active_subscription
from app.db.supabase_client import get_supabase


# Helper: create minimal valid PDF bytes
def create_valid_pdf_bytes() -> bytes:
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Patient Lab Report: Hemoglobin 14.2 g/dL (Normal: 13.0 - 17.0)")
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# Helper: create minimal valid JPEG bytes
def create_valid_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# Helper: create minimal valid PNG bytes
def create_valid_png_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─── 1. Filename Sanitization Tests ──────────────────────────────
def test_sanitize_filename_traversal():
    dirty = "../../../secrets/patient_data.pdf"
    clean = _sanitize_filename(dirty)
    assert ".." not in clean
    assert "/" not in clean
    assert clean.endswith("patient_data.pdf")


def test_sanitize_filename_null_bytes():
    dirty = "report\x00_2026.pdf"
    clean = _sanitize_filename(dirty)
    assert "\x00" not in clean


def test_sanitize_filename_empty():
    clean = _sanitize_filename("   ")
    assert clean.startswith("medical_report_")


# ─── 2. File Validation: Valid Files ─────────────────────────────
def test_validate_valid_pdf():
    pdf_bytes = create_valid_pdf_bytes()
    ext = _validate_file(pdf_bytes, "application/pdf")
    assert ext == "pdf"


def test_validate_valid_jpeg():
    jpeg_bytes = create_valid_jpeg_bytes()
    ext = _validate_file(jpeg_bytes, "image/jpeg")
    assert ext == "jpg"


def test_validate_valid_png():
    png_bytes = create_valid_png_bytes()
    ext = _validate_file(png_bytes, "image/png")
    assert ext == "png"


# ─── 3. File Validation: Malicious & Corrupted Files ──────────────
def test_validate_empty_file():
    with pytest.raises(HTTPException) as exc:
        _validate_file(b"", "application/pdf")
    assert exc.value.status_code == 400
    assert "empty" in exc.value.detail


def test_validate_oversized_file():
    # 21 MB dummy bytes
    big_bytes = b"0" * (21 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        _validate_file(big_bytes, "application/pdf")
    assert exc.value.status_code == 400
    assert "exceeds" in exc.value.detail


def test_validate_malicious_pe_executable():
    # Windows PE executable header MZ
    malicious_bytes = b"MZ\x90\x00\x03\x00\x00\x00" + b"A" * 100
    with pytest.raises(HTTPException) as exc:
        _validate_file(malicious_bytes, "application/pdf")
    assert exc.value.status_code == 400
    assert "Executable or script payload detected" in exc.value.detail


def test_validate_malicious_html_payload():
    malicious_bytes = b"<!DOCTYPE html><html><script>alert(1)</script></html>"
    with pytest.raises(HTTPException) as exc:
        _validate_file(malicious_bytes, "image/jpeg")
    assert exc.value.status_code == 400
    assert "Executable or script payload detected" in exc.value.detail


def test_validate_corrupted_pdf():
    # Starts with %PDF but broken afterwards
    corrupt_pdf = b"%PDF-1.4\nCorrupted binary garbage not a valid pdf document"
    with pytest.raises(HTTPException) as exc:
        _validate_file(corrupt_pdf, "application/pdf")
    assert exc.value.status_code == 400
    assert "Corrupted or invalid PDF" in exc.value.detail


def test_validate_corrupted_jpeg():
    # Starts with JPEG marker \xff\xd8\xff but truncated
    corrupt_jpeg = b"\xff\xd8\xff\xe0truncated_bytes"
    with pytest.raises(HTTPException) as exc:
        _validate_file(corrupt_jpeg, "image/jpeg")
    assert exc.value.status_code == 400
    assert "Corrupted or invalid JPEG" in exc.value.detail


# ─── 4. Endpoint Integration: Upload & Ownership ─────────────────
def test_upload_report_endpoint_success():
    client = TestClient(app)
    user_id = "user-uuid-123"
    mock_user = {"id": user_id, "email": "patient@example.com", "email_confirmed": True}

    mock_supabase = MagicMock()
    # Mock storage upload
    mock_supabase.storage.from_.return_value.upload.return_value = {"Key": "test"}
    # Mock database insert
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "new-report"}]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"status": "EXTRACTED"}]

    app.dependency_overrides[require_active_subscription] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        pdf_bytes = create_valid_pdf_bytes()
        response = client.post(
            "/api/v1/reports/upload",
            files={"file": ("test_report.pdf", pdf_bytes, "application/pdf")},
            data={"report_name": "Routine CBC Blood Test"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "report_id" in data
        assert data["report_name"] == "Routine CBC Blood Test"
        assert data["processing_status"] in ("EXTRACTED", "NEEDS_REVIEW")

        # Verify storage upload path contains user_id folder (ownership isolation)
        upload_call = mock_supabase.storage.from_.return_value.upload.call_args
        storage_path = upload_call.kwargs.get("path") or upload_call[1].get("path")
        assert storage_path.startswith(f"{user_id}/")
    finally:
        app.dependency_overrides.clear()


def test_upload_report_unauthorized():
    client = TestClient(app)
    pdf_bytes = create_valid_pdf_bytes()
    # No auth header supplied
    response = client.post(
        "/api/v1/reports/upload",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 401


def test_download_url_ownership_isolation():
    client = TestClient(app)
    user_id = "authorized-user"
    report_id = "report-abc"
    mock_user = {"id": user_id, "email": "user@test.com", "email_confirmed": True}

    mock_supabase = MagicMock()
    # Report belongs to user_id
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": report_id,
        "user_id": user_id,
        "file_path": f"{user_id}/{report_id}/test.pdf",
    }
    mock_supabase.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": "https://supabase.co/storage/v1/object/sign/medical-reports/signed-url?token=xyz"
    }

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get(f"/api/v1/reports/{report_id}/download-url")
        assert response.status_code == 200
        data = response.json()
        assert "signed_url" in data
        assert data["expires_in"] == 3600
    finally:
        app.dependency_overrides.clear()


def test_download_url_forbidden_other_user():
    client = TestClient(app)
    user_id = "attacker-user"
    report_id = "other-users-report"
    mock_user = {"id": user_id, "email": "attacker@test.com", "email_confirmed": True}

    mock_supabase = MagicMock()
    # Report is NOT owned by attacker (returns None data)
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get(f"/api/v1/reports/{report_id}/download-url")
        assert response.status_code == 404
        assert "Report not found" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
