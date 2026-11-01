"""
Comprehensive unit and integration tests for MediExplain AI Phase 5:
Healthcare Dashboard Summary Stats, Report History & Filtering,
Report Details & Parameter Transparency, Doctor-Question Generator & Discussion Tracking.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from main import app
from app.core.dependencies import get_current_user
from app.db.supabase_client import get_supabase


client = TestClient(app)

OWNER_USER_ID = "user-patient-001"
OTHER_USER_ID = "user-intruder-999"
REPORT_ID = "report-cbc-1234"
QUESTION_ID = "question-hgb-5678"


@pytest.fixture
def mock_owner():
    return {
        "id": OWNER_USER_ID,
        "email": "patient@example.com",
        "email_confirmed": True,
        "role": "authenticated",
    }


@pytest.fixture
def mock_intruder():
    return {
        "id": OTHER_USER_ID,
        "email": "intruder@example.com",
        "email_confirmed": True,
        "role": "authenticated",
    }


# ─── 1. Dashboard Summary Statistics (/api/v1/reports/stats) ─────────

def test_dashboard_stats_calculation(mock_owner):
    """
    Test that dashboard stats aggregate total reports, completed explanations,
    items awaiting review, and in-progress processing.
    """
    mock_supabase = MagicMock()
    # Mock return 4 reports with varied statuses
    mock_reports = [
        {"id": "r1", "processing_status": "COMPLETED"},
        {"id": "r2", "processing_status": "COMPLETED"},
        {"id": "r3", "processing_status": "NEEDS_REVIEW"},
        {"id": "r4", "processing_status": "ANALYZING"},
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = mock_reports

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get("/api/v1/reports/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_reports"] == 4
        assert stats["completed_explanations"] == 2
        assert stats["needs_review"] == 1
        assert stats["processing"] == 1

        # Verify eq("user_id", OWNER_USER_ID) was called for isolation
        mock_supabase.table.assert_called_with("medical_reports")
        mock_supabase.table.return_value.select.return_value.eq.assert_called_with(
            "user_id", OWNER_USER_ID
        )
    finally:
        app.dependency_overrides.clear()


def test_dashboard_stats_empty_state(mock_owner):
    """
    Verify clean zero counts when the user has uploaded no reports yet.
    """
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get("/api/v1/reports/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_reports"] == 0
        assert stats["completed_explanations"] == 0
        assert stats["needs_review"] == 0
        assert stats["processing"] == 0
    finally:
        app.dependency_overrides.clear()


# ─── 2. Report Listing & History (/api/v1/reports/) ──────────────────

def test_list_reports_for_authenticated_user(mock_owner):
    """
    Ensure report history lists only reports belonging to current user ordered by creation.
    """
    mock_supabase = MagicMock()
    mock_reports = [
        {
            "id": "r1",
            "report_name": "Lipid Profile Oct 2026",
            "file_type": "pdf",
            "processing_status": "COMPLETED",
            "created_at": "2026-10-31T12:00:00Z",
        },
        {
            "id": "r2",
            "report_name": "Complete Blood Count",
            "file_type": "jpg",
            "processing_status": "NEEDS_REVIEW",
            "created_at": "2026-10-25T10:00:00Z",
        },
    ]
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    ).data = mock_reports

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get("/api/v1/reports/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["reports"]) == 2
        assert data["reports"][0]["report_name"] == "Lipid Profile Oct 2026"
    finally:
        app.dependency_overrides.clear()


# ─── 3. Report Details & Ownership Protection ────────────────────────

def test_get_report_details_owner_success(mock_owner):
    """Owner can access their own report details."""
    mock_supabase = MagicMock()
    report_data = {
        "id": REPORT_ID,
        "user_id": OWNER_USER_ID,
        "report_name": "Thyroid Function Test",
        "processing_status": "COMPLETED",
    }
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = report_data

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get(f"/api/v1/reports/{REPORT_ID}")
        assert response.status_code == 200
        assert response.json()["id"] == REPORT_ID
        assert response.json()["report_name"] == "Thyroid Function Test"
    finally:
        app.dependency_overrides.clear()


def test_get_report_details_non_owner_blocked(mock_intruder):
    """Intruder cannot access another user's report (returns 404)."""
    mock_supabase = MagicMock()
    # Supabase query with .eq("id", REPORT_ID).eq("user_id", OTHER_USER_ID) returns no data
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = None

    app.dependency_overrides[get_current_user] = lambda: mock_intruder
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get(f"/api/v1/reports/{REPORT_ID}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Report not found"
    finally:
        app.dependency_overrides.clear()


# ─── 4. Extracted Parameters for Report ──────────────────────────────

def test_get_report_parameters_success(mock_owner):
    """Retrieve extracted laboratory parameters for an authorized report."""
    mock_supabase = MagicMock()
    # Report ownership check
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = {"id": REPORT_ID}

    # Parameters query
    params_data = [
        {
            "id": "p1",
            "parameter_name": "Hemoglobin",
            "observed_value": "11.2",
            "unit": "g/dL",
            "reference_min": 13.0,
            "reference_max": 17.0,
            "reference_text": "13.0 - 17.0 g/dL",
            "laboratory_flag": "L",
            "extraction_confidence": 0.98,
            "needs_user_review": False,
            "user_confirmed": False,
        },
        {
            "id": "p2",
            "parameter_name": "Platelets",
            "observed_value": "240",
            "unit": "10^3/uL",
            "reference_min": 150.0,
            "reference_max": 450.0,
            "reference_text": "150 - 450 10^3/uL",
            "laboratory_flag": None,
            "extraction_confidence": 0.95,
            "needs_user_review": False,
            "user_confirmed": False,
        },
    ]
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    ).data = params_data

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get(f"/api/v1/reports/{REPORT_ID}/parameters")
        assert response.status_code == 200
        params = response.json()["parameters"]
        assert len(params) == 2
        assert params[0]["parameter_name"] == "Hemoglobin"
        assert params[0]["laboratory_flag"] == "L"
        assert params[1]["observed_value"] == "240"
    finally:
        app.dependency_overrides.clear()


# ─── 5. Doctor Questions Endpoints ───────────────────────────────────

def test_get_doctor_questions_for_report(mock_owner):
    """Retrieve doctor questions for an authorized report."""
    mock_supabase = MagicMock()
    # Report ownership check passes
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = {"id": REPORT_ID}

    # Questions query
    questions_data = [
        {
            "id": QUESTION_ID,
            "report_id": REPORT_ID,
            "question_order": 1,
            "question": "My hemoglobin is 11.2 g/dL, which is below the reference range. Could this be related to iron deficiency or recent fatigue?",
            "priority": "HIGH",
            "related_parameter": "Hemoglobin",
            "discussion_status": "PENDING",
        },
        {
            "id": "q2",
            "report_id": REPORT_ID,
            "question_order": 2,
            "question": "Should I follow up with a serum ferritin or iron studies panel?",
            "priority": "MEDIUM",
            "related_parameter": "Hemoglobin",
            "discussion_status": "PENDING",
        },
    ]
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    ).data = questions_data

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get(f"/api/v1/questions/report/{REPORT_ID}")
        assert response.status_code == 200
        questions = response.json()["questions"]
        assert len(questions) == 2
        assert questions[0]["priority"] == "HIGH"
        assert questions[0]["discussion_status"] == "PENDING"
    finally:
        app.dependency_overrides.clear()


def test_update_doctor_question_discussion_status(mock_owner):
    """Toggle doctor question status between PENDING and DISCUSSED."""
    mock_supabase = MagicMock()
    # Ownership verification: .select("*, medical_reports!inner(user_id)").eq(...).eq(...).single().execute()
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = {"id": QUESTION_ID, "report_id": REPORT_ID}

    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {"id": QUESTION_ID, "discussion_status": "DISCUSSED"}
    ]

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        # 1. Update to DISCUSSED
        response = client.patch(
            f"/api/v1/questions/{QUESTION_ID}/status",
            json={"discussion_status": "DISCUSSED"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Status updated"

        # Verify Supabase update call
        mock_supabase.table.return_value.update.assert_called_with(
            {"discussion_status": "DISCUSSED"}
        )

        # 2. Test invalid status rejection
        invalid_response = client.patch(
            f"/api/v1/questions/{QUESTION_ID}/status",
            json={"discussion_status": "UNKNOWN_STATUS"},
        )
        assert invalid_response.status_code == 400
        assert "discussion_status must be 'PENDING' or 'DISCUSSED'" in invalid_response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_update_doctor_question_cross_user_forbidden(mock_intruder):
    """An unauthorized user cannot update questions from another user's report."""
    mock_supabase = MagicMock()
    # Inner join fails to find matching record for intruder user_id
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = None

    app.dependency_overrides[get_current_user] = lambda: mock_intruder
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.patch(
            f"/api/v1/questions/{QUESTION_ID}/status",
            json={"discussion_status": "DISCUSSED"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Question not found"
    finally:
        app.dependency_overrides.clear()


# ─── 6. Delete Report Endpoint ───────────────────────────────────────

def test_delete_report_success(mock_owner):
    """Owner can delete their report along with storage file."""
    mock_supabase = MagicMock()
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = {"id": REPORT_ID, "file_path": f"{OWNER_USER_ID}/{REPORT_ID}/blood_test.pdf"}

    mock_supabase.storage.from_.return_value.remove.return_value = [{"name": "blood_test.pdf"}]
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [{"id": REPORT_ID}]

    app.dependency_overrides[get_current_user] = lambda: mock_owner
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.delete(f"/api/v1/reports/{REPORT_ID}")
        assert response.status_code == 200
        assert response.json()["message"] == "Report deleted successfully"
        mock_supabase.storage.from_.return_value.remove.assert_called_with([f"{OWNER_USER_ID}/{REPORT_ID}/blood_test.pdf"])
    finally:
        app.dependency_overrides.clear()


def test_delete_report_non_owner_blocked(mock_intruder):
    """Non-owner cannot delete another user's report."""
    mock_supabase = MagicMock()
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value
    ).data = None

    app.dependency_overrides[get_current_user] = lambda: mock_intruder
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.delete(f"/api/v1/reports/{REPORT_ID}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Report not found"
    finally:
        app.dependency_overrides.clear()
