"""
MediExplain AI — Comprehensive Phase 4 Test Suite.
Tests Gemini-powered medical report explanations, medical safety guardrails,
schema validations, unconfirmed parameter quarantine, error handling,
and ownership isolation.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from app.core.config import settings
from app.core.dependencies import get_current_user, require_active_subscription
from app.db.supabase_client import get_supabase
from app.services.ai.gemini_service import (
    generate_overall_summary,
    generate_parameter_explanation,
    sanitize_and_verify_medical_safety,
    _extract_json,
    _get_model,
)
from app.schemas.analysis import OverallSummarySchema, ParameterExplanationSchema


# ─── 1. Medical Safety Guardrail Tests ────────────────────────────────
def test_sanitize_medical_safety_neutralizes_diagnoses():
    dangerous_text = "Based on this glucose of 145, you have diabetes and your diagnosis is diabetes."
    sanitized = sanitize_and_verify_medical_safety(dangerous_text)
    assert "you have diabetes" not in sanitized.lower()
    assert "diagnosis is diabetes" not in sanitized.lower()
    assert "clinical evaluation" in sanitized.lower() or "physician" in sanitized.lower()


def test_sanitize_medical_safety_neutralizes_prescriptions():
    dangerous_text = "You should start taking 500 mg metformin daily to lower this level."
    sanitized = sanitize_and_verify_medical_safety(dangerous_text)
    assert "start taking 500 mg" not in sanitized.lower()
    assert "warrants clinical evaluation" in sanitized.lower()


def test_sanitize_medical_safety_preserves_educational_text():
    safe_text = "Hemoglobin is an iron-rich protein in red blood cells that transports oxygen throughout the body."
    result = sanitize_and_verify_medical_safety(safe_text)
    assert result == safe_text


# ─── 2. JSON Extraction & Schema Validation Tests ─────────────────────
def test_extract_json_from_clean_string():
    raw = '{"report_type": "Lipid Profile", "overall_assessment": "Normal"}'
    parsed = _extract_json(raw)
    assert parsed["report_type"] == "Lipid Profile"


def test_extract_json_from_markdown_code_fences():
    raw = 'Here is the summary:\n```json\n{"report_type": "CBC", "overall_assessment": "Stable"}\n```'
    parsed = _extract_json(raw)
    assert parsed["report_type"] == "CBC"


def test_extract_json_malformed_raises_value_error():
    with pytest.raises(ValueError) as exc:
        _extract_json("Not a json at all")
    assert "Could not extract valid JSON" in str(exc.value)


def test_schema_validation_rejects_missing_required_fields():
    incomplete_data = {"report_type": "CBC"}  # Missing overall_assessment
    with pytest.raises(Exception):
        OverallSummarySchema.model_validate(incomplete_data)


# ─── 3. Missing Reference Ranges in AI Prompts (No Invention) ─────────
@pytest.mark.asyncio
async def test_missing_reference_range_passes_not_reported():
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "parameter_name": "Alkaline Phosphatase",
        "observed_value": "95.0",
        "unit": "U/L",
        "reference_range": "Not reported by laboratory",
        "classification": "UNKNOWN",
        "what_it_measures": "An enzyme found in liver and bones.",
        "simple_explanation": "Level measured at 95.0 U/L without a laboratory reference range.",
        "contextual_limitations": "Reference range not reported by the performing facility.",
        "when_to_seek_attention": "Discuss with your physician.",
        "doctor_questions": ["What is your reference range for this test?"],
        "disclaimer": "Informational only."
    })
    mock_model.generate_content.return_value = mock_response

    param = {
        "parameter_name": "Alkaline Phosphatase",
        "observed_value": "95.0",
        "unit": "U/L",
        "reference_text": None,  # Missing reference range
        "laboratory_flag": None,
    }

    with patch("app.services.ai.gemini_service._get_model", return_value=mock_model):
        result = await generate_parameter_explanation(param)
        assert result["parameter_name"] == "Alkaline Phosphatase"
        assert result["classification"] == "UNKNOWN"
        # Check prompt sent to model contained "Not reported"
        prompt_called = mock_model.generate_content.call_args[0][0]
        assert "Not reported by laboratory" in prompt_called


# ─── 4. Error Handling: Timeouts, 429 Rate Limits, Missing Key ────────
@pytest.mark.asyncio
async def test_gemini_timeout_raises_504():
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = Exception("Connection timeout while contacting Gemini API")

    with patch("app.services.ai.gemini_service._get_model", return_value=mock_model):
        with pytest.raises(HTTPException) as exc:
            await generate_parameter_explanation({"parameter_name": "Glucose"})
        assert exc.value.status_code == 504
        assert "timed out" in exc.value.detail


@pytest.mark.asyncio
async def test_gemini_quota_limit_raises_429():
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = Exception("Resource has been exhausted (e.g. check quota 429)")

    with patch("app.services.ai.gemini_service._get_model", return_value=mock_model):
        with pytest.raises(HTTPException) as exc:
            await generate_parameter_explanation({"parameter_name": "Glucose"})
        assert exc.value.status_code == 429
        assert "rate limit reached" in exc.value.detail


def test_gemini_missing_api_key_raises_503():
    with patch.object(settings, "AI_API_KEY", ""):
        with patch("app.services.ai.gemini_service._model", None):
            with pytest.raises(HTTPException) as exc:
                _get_model()
            assert exc.value.status_code == 503
            assert "AI explanation service is not configured" in exc.value.detail


# ─── 5. Trigger Analysis Endpoint & Unconfirmed Parameter Quarantine ──
def test_trigger_analysis_skips_unconfirmed_parameters():
    client = TestClient(app)
    user_id = "user-123"
    report_id = "rep-555"
    mock_user = {"id": user_id, "email": "test@test.com", "email_confirmed": True}

    mock_supabase = MagicMock()
    # Mock report ownership
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": report_id,
        "processing_status": "EXTRACTED",
        "report_name": "Blood Report",
        "user_id": user_id,
    }

    # Two parameters: one confirmed, one UNCONFIRMED requiring review
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": "p1",
            "parameter_name": "Hemoglobin",
            "observed_value": "14.2",
            "unit": "g/dL",
            "reference_text": "13.0 - 17.0",
            "needs_user_review": False,
            "user_confirmed": True,
        },
        {
            "id": "p2",
            "parameter_name": "Serum Creatinine",
            "observed_value": "1O..2",
            "unit": "mg/dL",
            "needs_user_review": True,
            "user_confirmed": False,  # UNCONFIRMED!
        },
    ]

    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "analysis-1"}]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []

    mock_summary = {
        "report_type": "CBC",
        "overall_assessment": "The confirmed parameters show normal hemoglobin.",
        "parameters_within_range": ["Hemoglobin"],
        "parameters_outside_range": [],
        "potentially_critical_flags": [],
        "missing_information": [],
        "key_limitations": ["Single test snapshot"],
        "doctor_discussion_questions": ["Is any follow up needed?"],
    }

    mock_p_exp = {
        "parameter_name": "Hemoglobin",
        "observed_value": "14.2",
        "unit": "g/dL",
        "reference_range": "13.0 - 17.0",
        "classification": "WITHIN_RANGE",
        "what_it_measures": "Oxygen carrying protein.",
        "simple_explanation": "Value is within the laboratory reference range.",
        "contextual_limitations": "Standard range.",
        "when_to_seek_attention": "Routine checkup.",
        "doctor_questions": [],
    }

    app.dependency_overrides[require_active_subscription] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    with patch("app.api.v1.endpoints.analysis.generate_overall_summary", AsyncMock(return_value=mock_summary)) as mock_gen_sum:
        with patch("app.api.v1.endpoints.analysis.generate_parameter_explanation", AsyncMock(return_value=mock_p_exp)) as mock_gen_exp:
            try:
                res = client.post(f"/api/v1/analysis/{report_id}/trigger")
                assert res.status_code == 200
                data = res.json()
                assert data["parameters_analyzed"] == 1
                assert data["unconfirmed_parameters_skipped"] == 1

                # Verify Gemini was called ONLY for the confirmed parameter
                assert mock_gen_exp.call_count == 1
                called_param = mock_gen_exp.call_args[0][0]
                assert called_param["parameter_name"] == "Hemoglobin"
            finally:
                app.dependency_overrides.clear()


# ─── 6. Cross-User Access Security ────────────────────────────────────
def test_analysis_cross_user_access_blocked():
    client = TestClient(app)
    attacker_user = {"id": "attacker-id", "email": "attacker@test.com", "email_confirmed": True}
    victim_report_id = "victim-report-id"

    mock_supabase = MagicMock()
    # Report query returns None because user_id does not match
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    app.dependency_overrides[require_active_subscription] = lambda: attacker_user
    app.dependency_overrides[get_current_user] = lambda: attacker_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        # Trigger blocked
        res_post = client.post(f"/api/v1/analysis/{victim_report_id}/trigger")
        assert res_post.status_code == 404
        assert "Report not found" in res_post.json()["detail"]

        # Get blocked
        res_get = client.get(f"/api/v1/analysis/{victim_report_id}")
        assert res_get.status_code == 404
        assert "Report not found" in res_get.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ─── 7. Real Gemini API Integration Test (Conditional) ────────────────
@pytest.mark.asyncio
async def test_real_gemini_api_integration():
    """
    Live Gemini API test.
    Automatically skips if AI_API_KEY is not set in backend/.env.
    Executes real live API call when key is provided.
    """
    if not settings.AI_API_KEY or settings.AI_API_KEY.strip() == "":
        pytest.skip("AI_API_KEY is not configured in backend/.env — skipping live Gemini integration test.")

    # Real live call
    test_params = [
        {
            "parameter_name": "Hemoglobin",
            "observed_value": "14.5",
            "unit": "g/dL",
            "reference_text": "13.0 - 17.0",
            "laboratory_flag": "N",
        }
    ]

    summary = await generate_overall_summary(test_params)
    assert "overall_assessment" in summary
    assert "parameters_within_range" in summary
    assert len(summary["doctor_discussion_questions"]) > 0

    exp = await generate_parameter_explanation(test_params[0])
    assert exp["parameter_name"] == "Hemoglobin"
    assert exp["classification"] in ("WITHIN_RANGE", "NORMAL")
    assert len(exp["what_it_measures"]) > 0

