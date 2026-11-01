"""
Unit tests for OCR Parameter Parser
Verifies extraction accuracy on fictional laboratory test reports
without inventing or hallucinating data.
"""
import pytest
from app.services.ocr.parameter_parser import parse_parameters, _parse_reference_range, _detect_flag


def test_clean_cbc_report_parsing():
    sample = """
    LIPID PROFILE TEST
    Cholesterol Total       215.0  mg/dL   < 200        H
    Triglycerides           160.0  mg/dL   < 150        H
    HDL Cholesterol         45.0   mg/dL   > 40         N
    LDL Cholesterol         138.0  mg/dL   < 100        H
    VLDL Cholesterol        32.0   mg/dL   < 30         H
    """
    params = parse_parameters(sample)
    assert len(params) == 5

    chol = next(p for p in params if "Cholesterol Total" in p["parameter_name"])
    assert chol["observed_value"] == "215.0"
    assert chol["unit"] == "mg/dL"
    assert chol["laboratory_flag"] == "H"

    hdl = next(p for p in params if "Hdl Cholesterol" in p["parameter_name"])
    assert hdl["observed_value"] == "45.0"
    assert hdl["unit"] == "mg/dL"


def test_reference_range_parser():
    min_val, max_val = _parse_reference_range("13.0 - 17.0")
    assert min_val == 13.0
    assert max_val == 17.0

    min_val, max_val = _parse_reference_range("< 200")
    assert min_val is None
    assert max_val == 200.0

    min_val, max_val = _parse_reference_range("> 40")
    assert min_val == 40.0
    assert max_val is None


def test_flag_detection():
    # Explicit flag takes precedence
    assert _detect_flag("Haemoglobin 11.2 g/dL 13-17 L", 11.2, 13.0, 17.0) == "L"
    assert _detect_flag("Glucose 140 mg/dL 70-100 HIGH", 140.0, 70.0, 100.0) == "H"

    # Inferred from range when explicit flag absent
    assert _detect_flag("WBC 3500 /cumm 4000-11000", 3500.0, 4000.0, 11000.0) == "L"
    assert _detect_flag("Platelets 250000 /cumm 150000-450000", 250000.0, 150000.0, 450000.0) == "N"

