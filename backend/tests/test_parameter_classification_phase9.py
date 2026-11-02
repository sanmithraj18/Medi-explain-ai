"""
MediExplain AI — Automated Test Suite for Phase 9: Medical Parameter Classification Consistency.
Tests:
1. Consistency between overview, parameter cards, counts, and urgent findings.
2. Missing laboratory reference ranges strictly map to RANGE_UNAVAILABLE (never WITHIN_RANGE).
3. Contextual clinical benchmark thresholds (ACC/AHA Guidelines) for LVEF and Blood Pressure.
4. LVEF of 40% classifies as BELOW_RANGE with ACC/AHA citation, counted in outside_range.
5. Absolute prohibition of heart failure diagnosis on ejection fraction alone.
6. Blood pressure safety:
   - Isolated systolic (missing diastolic) classifies as INCOMPLETE_ASSESSMENT (never complete category).
   - Diastolic measurement and repeated readings explained as necessary for staging.
   - Distinguishes isolated systolic above optimal (<120) from confirmed hypertension.
   - Pediatric patients (<18 years) trigger PEDIATRIC_INTERPRETATION_REQUIRED (AAP guideline percentiles).
   - Complete readings (both systolic & diastolic) evaluated per ACC/AHA categories.
   - Absolute prohibition of diagnosing hypertension from an isolated reading.
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
    evaluate_blood_pressure,
    parse_blood_pressure_values,
    detect_patient_age,
    LVEF_SOURCE,
    BP_SOURCE,
    AAP_SOURCE,
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
    # Explicitly notes that EF alone does not diagnose heart failure
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
    """Do not diagnose heart failure based on ejection fraction alone."""
    dangerous_explanation = (
        "Based on your ejection fraction of 40%, you have congestive heart failure and you are diagnosed with heart failure."
    )
    sanitized = sanitize_and_verify_medical_safety(dangerous_explanation)

    assert "you have congestive heart failure" not in sanitized.lower()
    assert "you are diagnosed with heart failure" not in sanitized.lower()
    assert "does not alone diagnose heart failure" in sanitized.lower()
    assert "clinical evaluation by a physician" in sanitized.lower()


# ─── 3. Blood Pressure: Missing Diastolic & Isolated Systolic Safety ───────────
def test_isolated_systolic_128_classified_as_incomplete_assessment():
    """
    Requirements 1, 2, 3, 4:
    A systolic blood pressure of 128 mmHg without diastolic reading MUST NOT
    be classified as 'Above Range' or complete hypertension.
    It MUST be classified as 'INCOMPLETE_ASSESSMENT' ('Incomplete Blood Pressure Assessment').
    """
    param = {
        "parameter_name": "Systolic Blood Pressure",
        "observed_value": "128 mmHg",
        "unit": "mmHg",
        "reference_text": None,
        "laboratory_flag": None,
    }
    result = classify_parameter(param)

    # 1. Do not assign complete category
    assert result["classification"] == "INCOMPLETE_ASSESSMENT"
    assert result["classification"] != "ABOVE_RANGE"
    assert result["classification"] != "WITHIN_RANGE"
    assert result["is_contextual_threshold"] is True
    assert result["clinical_source"] == BP_SOURCE

    notes = result["contextual_notes"]
    # 2 & 3. Explains diastolic measurement and repeated readings needed
    assert "Incomplete Blood Pressure Assessment" in notes
    assert "concurrent diastolic" in notes
    assert "repeated readings" in notes
    # 4. Distinguishes isolated systolic above optimal threshold from confirmed hypertension
    assert "optimal adult systolic threshold (< 120 mmHg)" in notes
    assert "does not establish a diagnosis of hypertension" in notes


def test_isolated_systolic_optimal_missing_diastolic_incomplete_assessment():
    """Systolic 115 mmHg with missing diastolic is also an incomplete assessment."""
    param = {
        "parameter_name": "Systolic BP",
        "observed_value": "115",
        "unit": "mmHg",
    }
    result = classify_parameter(param)
    assert result["classification"] == "INCOMPLETE_ASSESSMENT"
    assert "optimal adult systolic range (< 120 mmHg)" in result["contextual_notes"]
    assert "concurrent diastolic measurement" in result["contextual_notes"]


def test_systolic_bp_hypertensive_crisis_threshold():
    """Systolic BP > 180 mmHg triggers CRITICAL threshold regardless of diastolic."""
    param = {
        "parameter_name": "Systolic BP",
        "observed_value": "195",
        "unit": "mmHg",
    }
    result = classify_parameter(param)
    assert result["classification"] == "CRITICAL"
    assert result["clinical_source"] == BP_SOURCE
    assert "hypertensive crisis" in result["contextual_notes"].lower()


# ─── 4. Blood Pressure: Complete Readings Evaluation ──────────────────────────
def test_complete_blood_pressure_readings_with_paired_parameters():
    """
    When BOTH systolic and diastolic pressures are available, evaluate complete
    reading per 2017 ACC/AHA guidelines.
    """
    # Case A: Normal (< 120 / < 80)
    all_params_normal = [
        {"parameter_name": "Systolic Blood Pressure", "observed_value": "118", "unit": "mmHg"},
        {"parameter_name": "Diastolic Blood Pressure", "observed_value": "76", "unit": "mmHg"},
    ]
    res_sys_norm = classify_parameter(all_params_normal[0], all_parameters=all_params_normal)
    assert res_sys_norm["classification"] == "WITHIN_RANGE"
    assert "118/76 mmHg" in res_sys_norm["contextual_notes"]

    # Case B: Elevated / Stage 1 (128 / 82)
    all_params_elevated = [
        {"parameter_name": "Systolic Blood Pressure", "observed_value": "128", "unit": "mmHg"},
        {"parameter_name": "Diastolic Blood Pressure", "observed_value": "82", "unit": "mmHg"},
    ]
    res_sys_elev = classify_parameter(all_params_elevated[0], all_parameters=all_params_elevated)
    assert res_sys_elev["classification"] == "ABOVE_RANGE"
    assert "128/82 mmHg" in res_sys_elev["contextual_notes"]
    assert "cannot diagnose hypertension" in res_sys_elev["contextual_notes"].lower()

    # Case C: Stage 2 (145 / 92)
    all_params_stage2 = [
        {"parameter_name": "Systolic Blood Pressure", "observed_value": "145", "unit": "mmHg"},
        {"parameter_name": "Diastolic Blood Pressure", "observed_value": "92", "unit": "mmHg"},
    ]
    res_sys_st2 = classify_parameter(all_params_stage2[0], all_parameters=all_params_stage2)
    assert res_sys_st2["classification"] == "ABOVE_RANGE"
    assert "145/92 mmHg" in res_sys_st2["contextual_notes"]
    assert "Stage 2" in res_sys_st2["contextual_notes"]
    assert "does not diagnose hypertension" in res_sys_st2["contextual_notes"].lower()


def test_complete_blood_pressure_slash_format():
    """Single combined parameter 'Blood Pressure: 120/80 mmHg'."""
    param_normal = {"parameter_name": "Blood Pressure", "observed_value": "118/76", "unit": "mmHg"}
    res_norm = classify_parameter(param_normal)
    assert res_norm["classification"] == "WITHIN_RANGE"

    param_st1 = {"parameter_name": "Blood Pressure", "observed_value": "128/82", "unit": "mmHg"}
    res_st1 = classify_parameter(param_st1)
    assert res_st1["classification"] == "ABOVE_RANGE"

    param_crisis = {"parameter_name": "Blood Pressure", "observed_value": "195/125", "unit": "mmHg"}
    res_crisis = classify_parameter(param_crisis)
    assert res_crisis["classification"] == "CRITICAL"


# ─── 5. Blood Pressure: Pediatric Rules (< 18 years) ─────────────────────────
def test_pediatric_blood_pressure_under_18_requires_age_specific_percentiles():
    """
    Requirement 5: Do not apply adult blood pressure thresholds automatically to users under 18.
    Require appropriate age-specific clinical interpretation per AAP guidelines.
    """
    param_pediatric = {
        "parameter_name": "Systolic Blood Pressure",
        "observed_value": "128",
        "unit": "mmHg",
        "patient_age": 15,  # Under 18
    }
    result = classify_parameter(param_pediatric)

    assert result["classification"] == "PEDIATRIC_INTERPRETATION_REQUIRED"
    assert result["is_contextual_threshold"] is True
    assert result["clinical_source"] == AAP_SOURCE
    assert "Adult ACC/AHA blood pressure benchmarks do not apply" in result["contextual_notes"]
    assert "age-, sex-, and height-specific percentiles" in result["contextual_notes"]
    assert "AAP" in result["contextual_notes"]


def test_pediatric_age_detected_from_all_parameters():
    """Verify patient age parameter in document triggers pediatric guardrail."""
    report_params = [
        {"parameter_name": "Patient Age", "observed_value": "14", "unit": "Years"},
        {"parameter_name": "Blood Pressure", "observed_value": "120/80", "unit": "mmHg"},
    ]
    res_bp = classify_parameter(report_params[1], all_parameters=report_params)
    assert res_bp["classification"] == "PEDIATRIC_INTERPRETATION_REQUIRED"
    assert res_bp["clinical_source"] == AAP_SOURCE


# ─── 6. Hypertension Diagnostic Neutralization (Safety Guardrail) ─────────────
def test_sanitize_neutralizes_hypertension_diagnoses():
    """
    Requirement 7: Do not diagnose hypertension from an isolated reading.
    """
    dangerous_text = (
        "Based on your blood pressure reading of 128/82, you have stage 1 hypertension and this confirms high blood pressure."
    )
    sanitized = sanitize_and_verify_medical_safety(dangerous_text)

    assert "you have stage 1 hypertension" not in sanitized.lower()
    assert "this confirms high blood pressure" not in sanitized.lower()
    assert "cannot diagnose hypertension" in sanitized.lower()
    assert "repeated measurements" in sanitized.lower()


# ─── 7. Missing Laboratory Reference Ranges (Never Within Range) ─────────────
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


# ─── 8. Critical Urgent Flags Consistency ────────────────────────────────────
def test_critical_urgent_flag_detection_and_consistency():
    """Keep urgent-result warnings consistent across overview and parameter cards."""
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


# ─── 9. Full Deterministic Reconciliation Test ────────────────────────────────
def test_reconcile_analysis_classifications_ensures_no_contradictions():
    """
    Requirement 6: Keep the overview counts consistent with individual parameter cards.
    Validates:
    - LVEF 40% -> outside_range
    - Isolated Systolic BP 128 mmHg (missing diastolic) -> parameters_unclassified
    - Ferritin (missing range) -> parameters_unclassified
    - Potassium 6.4 -> critical_flags & outside_range
    - Hemoglobin (normal) -> parameters_within_range
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
            "observed_value": "128",
            "unit": "mmHg",
            "reference_text": None,  # Diastolic is missing!
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

    detailed_explanation = {
        "Left Ventricular Ejection Fraction": {
            "parameter_name": "Left Ventricular Ejection Fraction",
            "observed_value": "40%",
            "classification": "UNKNOWN",
            "simple_explanation": "Reduced left ventricular function.",
        },
        "Systolic Blood Pressure": {
            "parameter_name": "Systolic Blood Pressure",
            "observed_value": "128",
            "classification": "ABOVE_RANGE",  # Erroneous uncoordinated LLM classification
            "simple_explanation": "Systolic pressure reading.",
        },
        "Serum Ferritin": {
            "parameter_name": "Serum Ferritin",
            "observed_value": "110",
            "classification": "WITHIN_RANGE",  # Erroneously called WITHIN_RANGE without range
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

    # 1. LVEF 40% -> outside_range (NOT within_range)
    lvef_exp = reconciled_detailed["Left Ventricular Ejection Fraction"]
    assert lvef_exp["classification"] == "BELOW_RANGE"
    assert lvef_exp["is_contextual_threshold"] is True
    assert lvef_exp["clinical_source"] == LVEF_SOURCE
    assert "Left Ventricular Ejection Fraction" in reconciled_overall["parameters_outside_range"]
    assert "Left Ventricular Ejection Fraction" not in reconciled_overall["parameters_within_range"]

    # 2. Isolated Systolic BP (128 mmHg without diastolic) -> parameters_unclassified
    sbp_exp = reconciled_detailed["Systolic Blood Pressure"]
    assert sbp_exp["classification"] == "INCOMPLETE_ASSESSMENT"
    assert sbp_exp["clinical_source"] == BP_SOURCE
    assert "Systolic Blood Pressure" in reconciled_overall["parameters_unclassified"]
    assert "Systolic Blood Pressure" not in reconciled_overall["parameters_outside_range"]
    assert "Systolic Blood Pressure" not in reconciled_overall["parameters_within_range"]

    # 3. Missing Range (Ferritin) -> parameters_unclassified
    ferritin_exp = reconciled_detailed["Serum Ferritin"]
    assert ferritin_exp["classification"] == "RANGE_UNAVAILABLE"
    assert "Serum Ferritin" in reconciled_overall["parameters_unclassified"]
    assert "Serum Ferritin" not in reconciled_overall["parameters_within_range"]
    assert "Serum Ferritin" not in reconciled_overall["parameters_outside_range"]

    # 4. Critical Finding (Potassium) -> critical_flags & outside_range
    k_exp = reconciled_detailed["Potassium"]
    assert k_exp["classification"] == "CRITICAL"
    assert "Potassium" in reconciled_overall["potentially_critical_flags"]
    assert "Potassium" in reconciled_overall["parameters_outside_range"]

    # 5. Within Range (Hemoglobin) -> parameters_within_range
    hgb_exp = reconciled_detailed["Hemoglobin"]
    assert hgb_exp["classification"] == "WITHIN_RANGE"
    assert "Hemoglobin" in reconciled_overall["parameters_within_range"]
    assert "Hemoglobin" not in reconciled_overall["parameters_outside_range"]

    # 6. Validate with Pydantic OverallSummarySchema
    validated_schema = OverallSummarySchema.model_validate(reconciled_overall)
    assert len(validated_schema.parameters_within_range) == 1  # Hemoglobin
    assert len(validated_schema.parameters_outside_range) == 2  # LVEF, Potassium
    assert len(validated_schema.parameters_unclassified) == 2  # Systolic BP (incomplete), Ferritin (no range)
    assert len(validated_schema.potentially_critical_flags) == 1  # Potassium


# ─── 10. Integration Test: Analysis Trigger Endpoint with Reconciled Schema ───
def test_trigger_analysis_endpoint_stores_reconciled_classifications():
    """
    Simulates trigger_analysis endpoint with mocked Gemini response containing
    LVEF 40% and isolated Systolic BP 128 mmHg, verifying consistent storage.
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
        "report_name": "Echocardiogram and Vitals",
        "user_id": user_id,
    }

    # Parameters: LVEF 40% and Systolic BP 128 mmHg (isolated)
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
            "parameter_name": "Systolic Blood Pressure",
            "observed_value": "128",
            "unit": "mmHg",
            "reference_text": None,
            "needs_user_review": False,
            "user_confirmed": True,
        },
    ]

    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "analysis-p9"}]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []

    mock_overall = {
        "report_type": "Cardiac & Vitals Report",
        "overall_assessment": "Echocardiogram reveals reduced systolic ejection fraction.",
        "parameters_within_range": [],
        "parameters_outside_range": ["Systolic Blood Pressure"],  # Uncoordinated LLM output
        "parameters_unclassified": [],
        "potentially_critical_flags": [],
        "missing_information": [],
        "key_limitations": [],
        "disclaimer": "Informational purpose.",
        "doctor_discussion_questions": ["What is the recommendation for this ejection fraction?"],
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

    mock_exp_sbp = {
        "parameter_name": "Systolic Blood Pressure",
        "observed_value": "128",
        "unit": "mmHg",
        "reference_range": "Not reported",
        "classification": "ABOVE_RANGE",  # Erroneous uncoordinated LLM output
        "what_it_measures": "Measures peak arterial pressure during cardiac contraction.",
        "simple_explanation": "Systolic pressure 128 mmHg.",
        "contextual_limitations": "Diastolic reading not available.",
        "when_to_seek_attention": "Discuss at routine checkup.",
        "doctor_questions": [],
        "disclaimer": "Informational only.",
    }

    mock_user = {"id": user_id, "email": "p9@test.com", "email_confirmed": True}

    app.dependency_overrides[require_active_subscription] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    with patch("app.api.v1.endpoints.analysis.generate_overall_summary", AsyncMock(return_value=mock_overall)), \
         patch("app.api.v1.endpoints.analysis.generate_parameter_explanation", AsyncMock(side_effect=[mock_exp_lvef, mock_exp_sbp])):

        try:
            resp = client.post(f"/api/v1/analysis/{report_id}/trigger")
            assert resp.status_code == 200

            # Verify insert called with reconciled record
            insert_calls = mock_supabase.table("report_analyses").insert.call_args_list
            assert len(insert_calls) >= 1
            inserted_record = insert_calls[0][0][0]

            stored_overall = inserted_record["overall_summary"]
            stored_detailed = inserted_record["detailed_explanation"]

            # LVEF must be in outside_range
            assert "Left Ventricular Ejection Fraction" in stored_overall["parameters_outside_range"]
            assert stored_detailed["Left Ventricular Ejection Fraction"]["classification"] == "BELOW_RANGE"
            assert stored_detailed["Left Ventricular Ejection Fraction"]["clinical_source"] == LVEF_SOURCE

            # Systolic BP (128 mmHg without diastolic) must be in parameters_unclassified
            assert "Systolic Blood Pressure" in stored_overall["parameters_unclassified"]
            assert "Systolic Blood Pressure" not in stored_overall["parameters_outside_range"]
            assert "Systolic Blood Pressure" not in stored_overall["parameters_within_range"]
            assert stored_detailed["Systolic Blood Pressure"]["classification"] == "INCOMPLETE_ASSESSMENT"
            assert stored_detailed["Systolic Blood Pressure"]["clinical_source"] == BP_SOURCE
        finally:
            app.dependency_overrides.clear()
