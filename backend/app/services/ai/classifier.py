"""
MediExplain AI — Authoritative Parameter Classification Engine.
Ensures 100% deterministic consistency across report overview, parameter cards,
counts, and urgent findings.

Clinical Sources Configured:
- ACC/AHA Guidelines for the Management of Heart Failure (LVEF evaluation)
- 2017 ACC/AHA High Blood Pressure Clinical Practice Guideline (Blood Pressure evaluation)
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.ocr.parameter_parser import CRITICAL_THRESHOLDS

# Clinical sources
LVEF_SOURCE = "ACC/AHA Guidelines for the Management of Heart Failure"
BP_SOURCE = "2017 ACC/AHA High Blood Pressure Clinical Practice Guideline"

# Recognized contextual parameter regex patterns
LVEF_PATTERN = re.compile(
    r"\b(left\s+ventricular\s+ejection\s+fraction|ejection\s+fraction|lvef|\bef\b)\b",
    re.IGNORECASE,
)
SYSTOLIC_BP_PATTERN = re.compile(
    r"\b(systolic\s+blood\s+pressure|systolic\s+bp|\bsbp\b|blood\s+pressure\s*-\s*systolic)\b",
    re.IGNORECASE,
)
DIASTOLIC_BP_PATTERN = re.compile(
    r"\b(diastolic\s+blood\s+pressure|diastolic\s+bp|\bdbp\b|blood\s+pressure\s*-\s*diastolic)\b",
    re.IGNORECASE,
)


def extract_numeric_value(val_str: Any) -> Optional[float]:
    """Safely extract a float value from various raw string formats."""
    if val_str is None:
        return None
    if isinstance(val_str, (int, float)):
        return float(val_str)
    # Match leading or embedded number (e.g., "40%", "40.5", ">120", "< 5.0", "140 mm Hg")
    m = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?", str(val_str).replace(",", ""))
    if m:
        try:
            return float(m.group(0))
        except (ValueError, TypeError):
            return None
    return None


def parse_reference_bounds(ref_text: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Extract numeric lower and upper bounds from reference text if present."""
    if not ref_text:
        return None, None
    clean = ref_text.strip()
    # Check for range: e.g. 70 - 99 or 70.0 – 99.0
    range_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[-–—]\s*([0-9]+(?:\.[0-9]+)?)", clean)
    if range_match:
        try:
            return float(range_match.group(1)), float(range_match.group(2))
        except (ValueError, TypeError):
            pass
    # Check for upper threshold: e.g. < 200, <= 200, Upto 200, Less than 200
    upper_match = re.search(r"(?:<|<=|≤|upto|up to|less than)\s*([0-9]+(?:\.[0-9]+)?)", clean, re.I)
    if upper_match:
        try:
            return None, float(upper_match.group(1))
        except (ValueError, TypeError):
            pass
    # Check for lower threshold: e.g. > 50, >= 50, Greater than 50
    lower_match = re.search(r"(?:>|>=|≥|greater than)\s*([0-9]+(?:\.[0-9]+)?)", clean, re.I)
    if lower_match:
        try:
            return float(lower_match.group(1)), None
        except (ValueError, TypeError):
            pass
    return None, None


def is_physiologically_critical(parameter_name: str, numeric_val: Optional[float], lab_flag: Optional[str]) -> bool:
    """Detect if a parameter meets acute clinical critical safety criteria."""
    if lab_flag and any(k in lab_flag.upper() for k in ("CRITICAL", "PANIC", "ALERT", "HH", "LL")):
        return True
    if numeric_val is None:
        return False
    for pattern, is_critical in CRITICAL_THRESHOLDS:
        if pattern.search(parameter_name):
            try:
                if is_critical(numeric_val):
                    return True
            except Exception:
                pass
    return False


def classify_parameter(
    param: Dict[str, Any],
    llm_classification: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Authoritative classification of a medical parameter.
    
    Enforces strict rules:
    1. Critical flags/thresholds trigger 'CRITICAL'.
    2. Contextual benchmarks (LVEF, Systolic BP, Diastolic BP) apply when recognized.
       - LVEF 40% is classified as BELOW_RANGE (ACC/AHA source, non-diagnostic of heart failure).
       - Systolic BP >= 120 is ABOVE_RANGE (2017 ACC/AHA source, non-diagnostic alone).
    3. Laboratory reference ranges are respected if printed.
    4. If laboratory range is missing and no contextual benchmark applies,
       the classification is strictly 'RANGE_UNAVAILABLE'. Never 'WITHIN_RANGE'.
    """
    name = param.get("parameter_name", "").strip()
    obs_val = param.get("observed_value")
    num_val = extract_numeric_value(obs_val)
    unit = param.get("unit")
    ref_text = param.get("reference_text") or param.get("reference_range")
    lab_flag = param.get("laboratory_flag")

    ref_min = param.get("reference_min")
    ref_max = param.get("reference_max")
    if (ref_min is None and ref_max is None) and ref_text:
        ref_min, ref_max = parse_reference_bounds(ref_text)

    # 1. Critical safety threshold check
    if is_physiologically_critical(name, num_val, lab_flag):
        return {
            "classification": "CRITICAL",
            "is_contextual_threshold": False,
            "clinical_source": None,
            "contextual_notes": (
                "Critical safety alert: This value represents a potentially urgent physiological finding. "
                "Immediate consultation with a physician or emergency medical care is advised."
            ),
        }

    # 2. Recognized Contextual Benchmark: Left Ventricular Ejection Fraction (LVEF)
    if LVEF_PATTERN.search(name):
        has_lab_range = bool(ref_min is not None or ref_max is not None or ref_text)
        if num_val is not None:
            if num_val < 50.0:
                return {
                    "classification": "BELOW_RANGE",
                    "is_contextual_threshold": True,
                    "clinical_source": LVEF_SOURCE,
                    "contextual_notes": (
                        "ACC/AHA clinical benchmark: Normal left ventricular ejection fraction is typically ≥ 50%. "
                        f"An ejection fraction of {int(num_val) if num_val.is_integer() else num_val}% reflects "
                        "reduced left ventricular systolic function. Crucially, ejection fraction alone does not diagnose "
                        "heart failure; heart failure is a clinical syndrome requiring evaluation of symptoms and clinical signs by a physician."
                    ),
                }
            elif 50.0 <= num_val <= 75.0:
                return {
                    "classification": "WITHIN_RANGE",
                    "is_contextual_threshold": not has_lab_range,
                    "clinical_source": LVEF_SOURCE if not has_lab_range else None,
                    "contextual_notes": (
                        "ACC/AHA clinical benchmark: Normal left ventricular ejection fraction is ≥ 50%. "
                        "Ejection fraction alone does not diagnose or exclude cardiac conditions without physician assessment."
                    ),
                }
            else:  # > 75.0%
                return {
                    "classification": "ABOVE_RANGE",
                    "is_contextual_threshold": not has_lab_range,
                    "clinical_source": LVEF_SOURCE if not has_lab_range else None,
                    "contextual_notes": (
                        "ACC/AHA clinical benchmark: Ejection fraction above 75% indicates a hyperdynamic state and warrants clinical correlation."
                    ),
                }

    # 3. Recognized Contextual Benchmark: Systolic Blood Pressure
    if SYSTOLIC_BP_PATTERN.search(name):
        has_lab_range = bool(ref_min is not None or ref_max is not None or ref_text)
        if num_val is not None:
            if num_val > 180.0:
                return {
                    "classification": "CRITICAL",
                    "is_contextual_threshold": True,
                    "clinical_source": BP_SOURCE,
                    "contextual_notes": (
                        "Isolated systolic blood pressure > 180 mmHg represents a potential hypertensive crisis threshold. "
                        "In accordance with the 2017 ACC/AHA Guideline, full blood pressure staging requires concurrent diastolic "
                        "measurement and urgent clinical evaluation."
                    ),
                }
            elif num_val >= 120.0:
                return {
                    "classification": "ABOVE_RANGE",
                    "is_contextual_threshold": True,
                    "clinical_source": BP_SOURCE,
                    "contextual_notes": (
                        "In accordance with the 2017 ACC/AHA High Blood Pressure Clinical Practice Guideline, normal systolic "
                        "blood pressure is < 120 mmHg. This is an isolated systolic reading; complete blood pressure staging "
                        "requires concurrent diastolic blood pressure and repeated clinical measurements."
                    ),
                }
            elif 90.0 <= num_val < 120.0:
                return {
                    "classification": "WITHIN_RANGE",
                    "is_contextual_threshold": not has_lab_range,
                    "clinical_source": BP_SOURCE if not has_lab_range else None,
                    "contextual_notes": (
                        "In accordance with the 2017 ACC/AHA Guideline, normal systolic blood pressure is < 120 mmHg. "
                        "A complete assessment requires concurrent diastolic blood pressure."
                    ),
                }
            else:  # < 90.0
                return {
                    "classification": "BELOW_RANGE",
                    "is_contextual_threshold": True,
                    "clinical_source": BP_SOURCE,
                    "contextual_notes": (
                        "Systolic blood pressure below 90 mmHg indicates hypotension. Complete evaluation requires concurrent diastolic measurement."
                    ),
                }

    # 4. Recognized Contextual Benchmark: Diastolic Blood Pressure
    if DIASTOLIC_BP_PATTERN.search(name):
        has_lab_range = bool(ref_min is not None or ref_max is not None or ref_text)
        if num_val is not None:
            if num_val > 120.0:
                return {
                    "classification": "CRITICAL",
                    "is_contextual_threshold": True,
                    "clinical_source": BP_SOURCE,
                    "contextual_notes": (
                        "Isolated diastolic blood pressure > 120 mmHg represents potential hypertensive crisis. "
                        "Requires concurrent systolic measurement and immediate clinical evaluation."
                    ),
                }
            elif num_val >= 80.0:
                return {
                    "classification": "ABOVE_RANGE",
                    "is_contextual_threshold": True,
                    "clinical_source": BP_SOURCE,
                    "contextual_notes": (
                        "In accordance with the 2017 ACC/AHA High Blood Pressure Clinical Practice Guideline, normal diastolic "
                        "blood pressure is < 80 mmHg. Complete assessment requires concurrent systolic measurement."
                    ),
                }
            elif 60.0 <= num_val < 80.0:
                return {
                    "classification": "WITHIN_RANGE",
                    "is_contextual_threshold": not has_lab_range,
                    "clinical_source": BP_SOURCE if not has_lab_range else None,
                    "contextual_notes": (
                        "In accordance with the 2017 ACC/AHA Guideline, normal diastolic blood pressure is < 80 mmHg."
                    ),
                }
            else:
                return {
                    "classification": "BELOW_RANGE",
                    "is_contextual_threshold": True,
                    "clinical_source": BP_SOURCE,
                    "contextual_notes": (
                        "Diastolic blood pressure below 60 mmHg indicates hypotension. Requires concurrent systolic measurement."
                    ),
                }

    # 5. Laboratory Printed Reference Range Evaluation
    has_printed_range = bool(ref_min is not None or ref_max is not None or ref_text)
    clean_flag = lab_flag.strip().upper() if lab_flag else None

    if has_printed_range:
        if num_val is not None:
            if ref_min is not None and num_val < ref_min:
                return {"classification": "BELOW_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            if ref_max is not None and num_val > ref_max:
                return {"classification": "ABOVE_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            
            # Numeric value is between bounds
            if clean_flag in ("H", "HIGH", "ABOVE"):
                return {"classification": "ABOVE_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            if clean_flag in ("L", "LOW", "BELOW"):
                return {"classification": "BELOW_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            
            # Normalize any LLM classification if bounds match
            if llm_classification in ("BELOW_RANGE", "SIGNIFICANTLY_BELOW") and ref_min is not None and num_val < ref_min:
                return {"classification": "BELOW_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            if llm_classification in ("ABOVE_RANGE", "SIGNIFICANTLY_ABOVE") and ref_max is not None and num_val > ref_max:
                return {"classification": "ABOVE_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}

            return {"classification": "WITHIN_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
        else:
            # Non-numeric with printed range (e.g. Negative, Non-Reactive)
            if clean_flag in ("H", "HIGH", "ABOVE", "POSITIVE", "REACTIVE"):
                return {"classification": "ABOVE_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            if clean_flag in ("L", "LOW", "BELOW"):
                return {"classification": "BELOW_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            if clean_flag in ("NORMAL", "N", "NEGATIVE", "NON-REACTIVE"):
                return {"classification": "WITHIN_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            
            if llm_classification in ("WITHIN_RANGE", "BELOW_RANGE", "ABOVE_RANGE"):
                return {"classification": llm_classification, "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}
            return {"classification": "WITHIN_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": None}

    # 6. Printed Laboratory Flag without printed numerical range
    if clean_flag in ("H", "HIGH", "ABOVE"):
        return {"classification": "ABOVE_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": "Identified as high by laboratory flag."}
    if clean_flag in ("L", "LOW", "BELOW"):
        return {"classification": "BELOW_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": "Identified as low by laboratory flag."}

    # 7. MISSING REFERENCE RANGE & NO CONTEXTUAL BENCHMARK
    # REQUIREMENT: Never classify as WITHIN_RANGE when reference range is missing.
    # Must be RANGE_UNAVAILABLE or NOT_CLASSIFIED / UNKNOWN.
    fallback_cls = (
        llm_classification
        if llm_classification in ("UNKNOWN", "NOT_CLASSIFIED", "RANGE_UNAVAILABLE")
        else "RANGE_UNAVAILABLE"
    )
    return {
        "classification": fallback_cls,
        "is_contextual_threshold": False,
        "clinical_source": None,
        "contextual_notes": "Reference range was not reported by the performing laboratory for this parameter.",
    }


def reconcile_analysis_classifications(
    overall_summary: Dict[str, Any],
    detailed_explanation: Dict[str, Any],
    confirmed_parameters: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Reconciles all parameter explanations and overall summary lists to ensure
    100% mathematical and clinical consistency.
    
    Guarantees:
    - Every parameter card's classification matches its status in overview lists.
    - No parameter is placed in 'parameters_within_range' if its range is missing.
    - LVEF 40% is in 'parameters_outside_range' and never 'parameters_within_range'.
    - Potentially critical flags are 1:1 consistent between overview and parameter cards.
    """
    within_range: List[str] = []
    outside_range: List[str] = []
    unclassified: List[str] = []
    critical_flags: List[str] = []

    for param in confirmed_parameters:
        name = param.get("parameter_name", "").strip()
        exp = detailed_explanation.get(name, {})
        llm_cls = exp.get("classification")

        # Compute authoritative classification
        auth_res = classify_parameter(param, llm_classification=llm_cls)
        final_cls = auth_res["classification"]

        # Update detailed explanation
        exp["classification"] = final_cls
        exp["is_contextual_threshold"] = auth_res["is_contextual_threshold"]
        exp["clinical_source"] = auth_res["clinical_source"]
        exp["contextual_notes"] = auth_res["contextual_notes"]

        if auth_res["contextual_notes"]:
            existing_limitations = exp.get("contextual_limitations", "")
            if auth_res["contextual_notes"] not in existing_limitations:
                exp["contextual_limitations"] = (
                    f"{auth_res['contextual_notes']} {existing_limitations}".strip()
                )

        detailed_explanation[name] = exp

        # Distribute into reconciled overview categories
        if final_cls == "CRITICAL":
            critical_flags.append(name)
            outside_range.append(name)
        elif final_cls in ("ABOVE_RANGE", "BELOW_RANGE"):
            outside_range.append(name)
        elif final_cls == "WITHIN_RANGE":
            within_range.append(name)
        else:  # RANGE_UNAVAILABLE, NOT_CLASSIFIED, UNKNOWN, UNCONFIRMED_OCR_VALUE
            unclassified.append(name)

    # Reconcile overall summary lists
    # Preserve order and avoid duplicates
    overall_summary["parameters_within_range"] = list(dict.fromkeys(within_range))
    overall_summary["parameters_outside_range"] = list(dict.fromkeys(outside_range))
    overall_summary["parameters_unclassified"] = list(dict.fromkeys(unclassified))
    overall_summary["potentially_critical_flags"] = list(dict.fromkeys(critical_flags))

    return overall_summary, detailed_explanation
