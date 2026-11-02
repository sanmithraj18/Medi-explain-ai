"""
MediExplain AI — Automated Test Suite for Phase 9: Medical Parameter Classification Consistency.
Tests:
1. Consistency between overview, parameter cards, counts, and urgent findings.
2. Missing laboratory reference ranges strictly map to RANGE_UNAVAILABLE (never WITHIN_RANGE).
3. Contextual clinical benchmark thresholds (ACC/AHA Guidelines) for LVEF and Blood Pressure.
4. LVEF of 40% classifies as BELOW_RANGE with ACC/AHA citation, counted in outside_range.
5. Absolute prohibition of heart failure diagnosis on ejection fraction alone.
6. Isolated systolic blood pressure restriction (incomplete staging without diastolic).
7. Critical urgent flag consistency between overview and parameter card.
8. Full end-to-end reconciliation prevents contradictory classifications across multi-parameter reports.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from app.services.ai.classifier import (
    classify_parameter,
    reconcile_analysis_classifications,
    extract_numeric_value,
    LVEF_SOURCE,
    BP_SOURCE,
)
from app.services.ai.gemini_service import sanitize_and_verify_medical_safety
from app.schemas.analysis import OverallSummarySchema, ParameterExplanationSchema


# ─── 1. Contextual Benchmark: Left Ventricular Ejection Fraction (LVEF) ───────
def test_lvef_40_percent_classified_as_below_range_with_clinical_source():
    """
    Requirement 5: Ensure ejection fraction of 40% is not displayed as 'Within Range'
    when the explanation identifies it as below the typical range.
    Requirement 4: Cite configured clinical source (ACC/AHA).
    """
    param = {
        "parameter_name": "Left Ventricular Ejection Fraction",
        "observed_value": "40%",
        "unit": "%",
        "reference_text": None,  # No lab reference range printed
        "laboratory_flag": None,
    }
    result = classify_parameter(param)

    assert result["classification"] == "BELOW_RANGE"
    assert result["is_contextual_threshold"] is True
    assert result["clinical_source"] == LVEF_SOURCE
    assert "ACC/AHA clinical benchmark" in result["contextual_notes"]
    assert "40%" in result["contextual_notes"]
    # Requirement 6: explicitly notes that EF alone does not diagnose heart failure
    assert "does not diagnose heart failure" in result["contextual_notes"]


def test_lvef_abbreviations_and_normal_threshold():
    """Verify EF abbreviations (LVEF, EF) and normal threshold >= 50%."""
    normal_param = {
        "parameter_name": "LVEF",
        "observed_value": "55",
        "unit": "%",
        "reference_text": None,
    }
    result = classify_parameter(normal_param)
    assert result["classification"] == "WITHIN_RANGE"
    assert result["clinical_source"] == LVEF_SOURCE

    low_ef_param = {
        "parameter_name": "Ejection Fraction (EF)",
        "observed_value": "35%",
        "unit": "%",
        "reference_text": None,
    }
    result_low = classify_parameter(low_ef_param)
    assert result_low["classification"] == "BELOW_RANGE"
    assert result_low["clinical_source"] == LVEF_SOURCE


# ─── 2. Heart Failure Diagnostic Prohibition ──────────────────────────────────
def test_sanitize_neutralizes_heart_failure_diagnosis():
    """
    Requirement 6: Do not diagnose heart failure based on ejection fraction alone.
    """
    dangerous_explanation = (
        "Based on your ejection fraction of 40%, you have congestive heart failure and you are diagnosed with heart failure."
    )
    sanitized = sanitize_and_verify_medical_safety(dangerous_explanation)

    assert "you have congestive heart failure" not in sanitized.lower()
    assert "you are diagnosed with heart failure" not in sanitized.lower()
    assert "does not alone diagnose heart failure" in sanitized.lower()
    assert "clinical evaluation by a physician" in sanitized.lower()


# ─── 3. Contextual Benchmark: Blood Pressure (Systolic BP) ────────────────────
def test_systolic_bp_classified_with_acc_aha_guideline_and_incomplete_warning():
    """
    Requirement 7: Do not classify systolic blood pressure independently as a complete blood-pressure assessment.
    Requirement 4: Cite configured clinical source (2017 ACC/AHA).
    """
    param = {
        "parameter_name": "Systolic Blood Pressure",
        "observed_value": "140 mmHg",
        "unit": "mmHg",
        "reference_text": None,
        "laboratory_flag": None,
    }
    result = classify_parameter(param)

    assert result["classification"] == "ABOVE_RANGE"
    assert result["is_contextual_threshold"] is True
    assert result["clinical_source"] == BP_SOURCE
    # Notes isolated systolic measurement requires concurrent diastolic
    assert "isolated systolic reading" in result["contextual_notes"]
    assert "concurrent diastolic" in result["contextual_notes"]


def test_systolic_bp_hypertensive_crisis_threshold():
    """Systolic BP > 180 mmHg triggers CRITICAL threshold."""
    param = {
        "parameter_name": "Systolic BP",
        "observed_value": "195",
        "unit": "mmHg",
    }
    result = classify_parameter(param)
    assert result["classification"] == "CRITICAL"
    assert result["clinical_source"] == BP_SOURCE
    assert "hypertensive crisis" in result["contextual_notes"].lower()


# ─── 4. Missing Laboratory Reference Ranges (Never Within Range) ─────────────
def test_missing_reference_range_never_classified_as_within_range():
    """
    Requirement 2: Never classify a parameter as 'Within Range' when its laboratory reference range is missing.
    Requirement 3: When the laboratory range is unavailable, display 'Reference Range Unavailable'.
    """
    param = {
        "parameter_name": "Alkaline Phosphatase",
        "observed_value": "85",
        "unit": "U/L",
        "reference_text": None,
        "reference_min": None,
        "reference_max": None,
        "laboratory_flag": None,
    }
    result = classify_parameter(param)

    assert result["classification"] == "RANGE_UNAVAILABLE"
    assert result["classification"] != "WITHIN_RANGE"
    assert result["is_contextual_threshold"] is False
    assert result["clinical_source"] is None


def test_override_llm_false_within_range_when_range_missing():
    """
    If LLM erroneously attempts to return WITHIN_RANGE when no reference range exists,
    authoritative classifier overrides to RANGE_UNAVAILABLE.
    """
    param = {
        "parameter_name": "Serum Ferritin",
        "observed_value": "120",
        "unit": "ng/mL",
        "reference_text": None,
    }
    result = classify_parameter(param, llm_classification="WITHIN_RANGE")
    assert result["classification"] == "RANGE_UNAVAILABLE"


# ─── 5. Critical Urgent Flags Consistency ────────────────────────────────────
def test_critical_urgent_flag_detection_and_consistency():
    """
    Requirement 8: Keep urgent-result warnings consistent across the overview and individual parameter cards.
    """
    # Critical Potassium
    param_k = {
        "parameter_name": "Potassium",
        "observed_value": "6.5",
        "unit": "mmol/L",
        "reference_text": "3.5 - 5.0",
        "laboratory_flag": "CRITICAL",
    }
    res_k = classify_parameter(param_k)
    assert res_k["classification"] == "CRITICAL"
    assert "critical safety alert" in res_k["contextual_notes"].lower()

    # Normal parameter
    param_normal = {
        "parameter_name": "Fasting Blood Glucose",
        "observed_value": "85",
        "unit": "mg/dL",
        "reference_text": "70 - 99",
        "reference_min": 70.0,
        "reference_max": 99.0,
    }
    res_normal = classify_parameter(param_normal)
    assert res_normal["classification"] == "WITHIN_RANGE"


# ─── 6. Full Deterministic Reconciliation Test ────────────────────────────────
def test_reconcile_analysis_classifications_ensures_no_contradictions():
    """
    Requirement 1: Use one consistent classification result across overview, parameter cards, counts, and urgent findings.
    Requirement 9: Validate classification logic using fictional test reports with missing ranges and abnormal results.
    Requirement 10: Automated tests to prevent contradictory classifications.
    """
    confirmed_params = [
        {
            "parameter_name": "Left Ventricular Ejection Fraction",
            "observed_value": "40%",
            "unit": "%",
            "reference_text": None,
        },
        {
            "parameter_name": "Systolic Blood Pressure",
            "observed_value": "135",
            "unit": "mmHg",
            "reference_text": None,
        },
        {
            "parameter_name": "Serum Ferritin",
            "observed_value": "110",
            "unit": "ng/mL",
            "reference_text": None,  # Missing range
        },
        {
            "parameter_name": "Potassium",
            "observed_value": "6.4",
            "unit": "mmol/L",
            "reference_text": "3.5 - 5.0",
            "laboratory_flag": "CRITICAL",
        },
        {
            "parameter_name": "Hemoglobin",
            "observed_value": "14.5",
            "unit": "g/dL",
            "reference_text": "13.0 - 17.0",
            "reference_min": 13.0,
            "reference_max": 17.0,
            "laboratory_flag": None,
        },
    ]

    # Simulated LLM explanations with potential inconsistencies
    detailed_explanation = {
        "Left Ventricular Ejection Fraction": {
            "parameter_name": "Left Ventricular Ejection Fraction",
            "observed_value": "40%",
            "classification": "UNKNOWN",  # LLM had UNKNOWN
            "simple_explanation": "Reduced left ventricular function.",
        },
        "Systolic Blood Pressure": {
            "parameter_name": "Systolic Blood Pressure",
            "observed_value": "135",
            "classification": "ABOVE_RANGE",
            "simple_explanation": "Elevated systolic reading.",
        },
        "Serum Ferritin": {
            "parameter_name": "Serum Ferritin",
            "observed_value": "110",
            "classification": "WITHIN_RANGE",  # LLM erroneously called it WITHIN_RANGE without a range
            "simple_explanation": "Ferritin measures iron stores.",
        },
        "Potassium": {
            "parameter_name": "Potassium",
            "observed_value": "6.4",
            "classification": "CRITICAL",
            "simple_explanation": "Significantly elevated potassium.",
        },
        "Hemoglobin": {
            "parameter_name": "Hemoglobin",
            "observed_value": "14.5",
            "classification": "WITHIN_RANGE",
            "simple_explanation": "Normal hemoglobin level.",
        },
    }

    overall_summary = {
        "report_type": "Multi-Panel Health Report",
        "overall_assessment": "Patient evaluation summary.",
        "parameters_within_range": [],
        "parameters_outside_range": [],
        "parameters_unclassified": [],
        "potentially_critical_flags": [],
        "missing_information": [],
        "key_limitations": [],
        "disclaimer": "Informational purpose.",
        "doctor_discussion_questions": ["What do these findings indicate?"],
    }

    reconciled_overall, reconciled_detailed = reconcile_analysis_classifications(
        overall_summary,
        detailed_explanation,
        confirmed_params,
    )

    # 1. Check LVEF 40%
    lvef_exp = reconciled_detailed["Left Ventricular Ejection Fraction"]
    assert lvef_exp["classification"] == "BELOW_RANGE"
    assert lvef_exp["is_contextual_threshold"] is True
    assert lvef_exp["clinical_source"] == LVEF_SOURCE
    assert "Left Ventricular Ejection Fraction" in reconciled_overall["parameters_outside_range"]
    assert "Left Ventricular Ejection Fraction" not in reconciled_overall["parameters_within_range"]

    # 2. Check Missing Reference Range (Serum Ferritin)
    ferritin_exp = reconciled_detailed["Serum Ferritin"]
    assert ferritin_exp["classification"] == "RANGE_UNAVAILABLE"
    assert "Serum Ferritin" in reconciled_overall["parameters_unclassified"]
    assert "Serum Ferritin" not in reconciled_overall["parameters_within_range"]
    assert "Serum Ferritin" not in reconciled_overall["parameters_outside_range"]

    # 3. Check Critical Finding (Potassium)
    k_exp = reconciled_detailed["Potassium"]
    assert k_exp["classification"] == "CRITICAL"
    assert "Potassium" in reconciled_overall["potentially_critical_flags"]
    assert "Potassium" in reconciled_overall["parameters_outside_range"]

    # 4. Check Within Range (Hemoglobin)
    hgb_exp = reconciled_detailed["Hemoglobin"]
    assert hgb_exp["classification"] == "WITHIN_RANGE"
    assert "Hemoglobin" in reconciled_overall["parameters_within_range"]
    assert "Hemoglobin" not in reconciled_overall["parameters_outside_range"]

    # 5. Check Systolic BP
    sbp_exp = reconciled_detailed["Systolic Blood Pressure"]
    assert sbp_exp["classification"] == "ABOVE_RANGE"
    assert sbp_exp["clinical_source"] == BP_SOURCE
    assert "Systolic Blood Pressure" in reconciled_overall["parameters_outside_range"]

    # 6. Validate with Pydantic OverallSummarySchema
    validated_schema = OverallSummarySchema.model_validate(reconciled_overall)
    assert len(validated_schema.parameters_within_range) == 1  # Hemoglobin
    assert len(validated_schema.parameters_outside_range) == 3  # LVEF, Systolic BP, Potassium
    assert len(validated_schema.parameters_unclassified) == 1  # Ferritin
    assert len(validated_schema.potentially_critical_flags) == 1  # Potassium


# ─── 7. Integration Test: Analysis Trigger Endpoint with Reconciled Schema ────
def test_trigger_analysis_endpoint_stores_reconciled_classifications():
    """
    Simulates trigger_analysis endpoint with mocked Gemini response containing
    LVEF 40% and a parameter with missing range, verifying consistent storage.
    """
    from unittest.mock import AsyncMock
    from app.core.dependencies import require_active_subscription
    from app.db.supabase_client import get_supabase

    client = TestClient(app)
    user_id = "test-user-p9"
    report_id = "rep-p9"

    mock_supabase = MagicMock()
    # Report ownership
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": report_id,
        "processing_status": "EXTRACTED",
        "report_name": "Echocardiogram and Lab",
        "user_id": user_id,
    }

    # Parameters: LVEF 40% (no range) and Total Bilirubin (no range)
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": "p1",
            "parameter_name": "Left Ventricular Ejection Fraction",
            "observed_value": "40%",
            "unit": "%",
            "reference_text": None,
            "needs_user_review": False,
            "user_confirmed": True,
        },
        {
            "id": "p2",
            "parameter_name": "Total Bilirubin",
            "observed_value": "0.9",
            "unit": "mg/dL",
            "reference_text": None,
            "needs_user_review": False,
            "user_confirmed": True,
        },
    ]

    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "analysis-p9"}]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []

    mock_overall = {
        "report_type": "Echocardiogram & Liver Panel",
        "overall_assessment": "Echocardiogram reveals reduced systolic ejection fraction.",
        "parameters_within_range": ["Left Ventricular Ejection Fraction"],  # Erroneous uncoordinated list
        "parameters_outside_range": [],
        "parameters_unclassified": [],
        "potentially_critical_flags": [],
        "missing_information": [],
        "key_limitations": [],
        "disclaimer": "Informational purpose.",
        "doctor_discussion_questions": ["What is the clinical recommendation for this ejection fraction?"],
    }

    mock_exp_lvef = {
        "parameter_name": "Left Ventricular Ejection Fraction",
        "observed_value": "40%",
        "unit": "%",
        "reference_range": "Not reported",
        "classification": "UNKNOWN",
        "what_it_measures": "Measures cardiac pumping efficiency.",
        "simple_explanation": "Ejection fraction at 40% is reduced.",
        "contextual_limitations": "Evaluated at resting state.",
        "when_to_seek_attention": "Consult your cardiologist.",
        "doctor_questions": [],
        "disclaimer": "Informational only.",
    }

    mock_exp_bili = {
        "parameter_name": "Total Bilirubin",
        "observed_value": "0.9",
        "unit": "mg/dL",
        "reference_range": "Not reported",
        "classification": "WITHIN_RANGE",  # Erroneously marked WITHIN_RANGE by LLM without a range
        "what_it_measures": "Liver function indicator.",
        "simple_explanation": "Bilirubin level 0.9 mg/dL.",
        "contextual_limitations": "No lab reference range provided.",
        "when_to_seek_attention": "Discuss at routine checkup.",
        "doctor_questions": [],
        "disclaimer": "Informational only.",
    }

    mock_user = {"id": user_id, "email": "p9@test.com", "email_confirmed": True}

    app.dependency_overrides[require_active_subscription] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    with patch("app.api.v1.endpoints.analysis.generate_overall_summary", AsyncMock(return_value=mock_overall)), \
         patch("app.api.v1.endpoints.analysis.generate_parameter_explanation", AsyncMock(side_effect=[mock_exp_lvef, mock_exp_bili])):

        try:
            resp = client.post(f"/api/v1/analysis/{report_id}/trigger")
            assert resp.status_code == 200

            # Verify insert called with reconciled record
            insert_calls = mock_supabase.table("report_analyses").insert.call_args_list
            assert len(insert_calls) >= 1
            inserted_record = insert_calls[0][0][0]

            stored_overall = inserted_record["overall_summary"]
            stored_detailed = inserted_record["detailed_explanation"]

            # LVEF must NOT be in within_range, MUST be in outside_range
            assert "Left Ventricular Ejection Fraction" not in stored_overall["parameters_within_range"]
            assert "Left Ventricular Ejection Fraction" in stored_overall["parameters_outside_range"]
            assert stored_detailed["Left Ventricular Ejection Fraction"]["classification"] == "BELOW_RANGE"
            assert stored_detailed["Left Ventricular Ejection Fraction"]["clinical_source"] == LVEF_SOURCE

            # Bilirubin must be in unclassified, NEVER in within_range
            assert "Total Bilirubin" in stored_overall["parameters_unclassified"]
            assert "Total Bilirubin" not in stored_overall["parameters_within_range"]
            assert stored_detailed["Total Bilirubin"]["classification"] == "RANGE_UNAVAILABLE"
        finally:
            app.dependency_overrides.clear()
