"""
MediExplain AI — Authoritative Parameter Classification Engine.
Ensures 100% deterministic consistency across report overview, parameter cards,
counts, and urgent findings.

Clinical Sources Configured:
- ACC/AHA Guidelines for the Management of Heart Failure (LVEF evaluation)
- 2017 ACC/AHA High Blood Pressure Clinical Practice Guideline (Blood Pressure evaluation)
- AAP Clinical Practice Guideline for Screening and Management of High Blood Pressure in Children and Adolescents (Pediatric BP)
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.ocr.parameter_parser import CRITICAL_THRESHOLDS

# Clinical sources
LVEF_SOURCE = "ACC/AHA Guidelines for the Management of Heart Failure"
BP_SOURCE = "2017 ACC/AHA High Blood Pressure Clinical Practice Guideline"
AAP_SOURCE = "AAP Clinical Practice Guideline for Screening and Management of High Blood Pressure in Children and Adolescents"

# Recognized contextual parameter regex patterns
LVEF_PATTERN = re.compile(
    r"\b(left\s+ventricular\s+ejection\s+fraction|ejection\s+fraction|lvef|\bef\b)\b",
    re.IGNORECASE,
)
COMBINED_BP_PATTERN = re.compile(
    r"^(?:arterial\s+)?(?:blood\s+pressure|\bnibp\b|\bbp\b)$",
    re.IGNORECASE,
)
SYSTOLIC_BP_PATTERN = re.compile(
    r"\b(systolic\s+blood\s+pressure|systolic\s+bp|\bsbp\b|blood\s+pressure\s*-\s*systolic|\bsystolic\b)\b",
    re.IGNORECASE,
)
DIASTOLIC_BP_PATTERN = re.compile(
    r"\b(diastolic\s+blood\s+pressure|diastolic\s+bp|\bdbp\b|blood\s+pressure\s*-\s*diastolic|\bdiastolic\b)\b",
    re.IGNORECASE,
)
AGE_PATTERN = re.compile(
    r"^\s*(?:patient\s+)?age\b",
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


def detect_patient_age(
    param: Optional[Dict[str, Any]] = None,
    all_parameters: Optional[List[Dict[str, Any]]] = None,
    explicit_age: Optional[float] = None,
) -> Optional[float]:
    """Detect patient age from explicit argument, parameter dict, or list of report parameters."""
    if explicit_age is not None:
        try:
            return float(explicit_age)
        except (ValueError, TypeError):
            pass

    if param and param.get("patient_age") is not None:
        try:
            return float(param["patient_age"])
        except (ValueError, TypeError):
            pass

    if all_parameters:
        for p in all_parameters:
            if p.get("patient_age") is not None:
                try:
                    return float(p["patient_age"])
                except (ValueError, TypeError):
                    pass
            p_name = p.get("parameter_name", "")
            if AGE_PATTERN.search(p_name):
                val = extract_numeric_value(p.get("observed_value"))
                if val is not None:
                    return float(val)

    return None


def parse_blood_pressure_values(
    param: Dict[str, Any],
    all_parameters: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Extracts systolic and diastolic values for blood pressure parameters.
    Returns: (systolic, diastolic, is_bp_parameter)
    """
    name = param.get("parameter_name", "").strip()
    obs_val = str(param.get("observed_value", "")).strip()

    # 1. Check for combined slash format: e.g. "128/82" or "120 / 80 mmHg"
    slash_match = re.search(r"([0-9]{2,3})\s*/\s*([0-9]{2,3})", obs_val)
    if slash_match:
        try:
            return float(slash_match.group(1)), float(slash_match.group(2)), True
        except (ValueError, TypeError):
            pass

    # 2. Check if this is explicitly a Systolic parameter
    if SYSTOLIC_BP_PATTERN.search(name):
        sys_val = extract_numeric_value(obs_val)
        dia_val = None
        if all_parameters:
            for p in all_parameters:
                p_name = p.get("parameter_name", "").strip()
                if p != param and DIASTOLIC_BP_PATTERN.search(p_name):
                    dia_val = extract_numeric_value(p.get("observed_value"))
                    break
        return sys_val, dia_val, True

    # 3. Check if this is explicitly a Diastolic parameter
    if DIASTOLIC_BP_PATTERN.search(name):
        dia_val = extract_numeric_value(obs_val)
        sys_val = None
        if all_parameters:
            for p in all_parameters:
                p_name = p.get("parameter_name", "").strip()
                if p != param and SYSTOLIC_BP_PATTERN.search(p_name):
                    sys_val = extract_numeric_value(p.get("observed_value"))
                    break
        return sys_val, dia_val, True

    # 4. Check if combined name "Blood Pressure" / "BP" without slash
    if COMBINED_BP_PATTERN.search(name):
        sys_val = extract_numeric_value(obs_val)
        return sys_val, None, True

    return None, None, False


def evaluate_blood_pressure(
    systolic: Optional[float],
    diastolic: Optional[float],
    patient_age: Optional[float] = None,
    has_lab_range: bool = False,
) -> Dict[str, Any]:
    """
    Safely evaluate blood pressure under ACC/AHA guidelines with strict medical boundaries:
    1. Does NOT apply adult cutoffs to patients under 18 years (requires AAP percentiles).
    2. Identifies acute hypertensive urgency/crisis (>180 systolic or >120 diastolic).
    3. If diastolic is missing, strictly assigns 'INCOMPLETE_ASSESSMENT' and explains
       concurrent diastolic & repeated clinical readings are required.
    4. Distinguishes an isolated systolic reading above optimal from confirmed hypertension.
    5. Evaluates complete readings (systolic + diastolic) against 2017 ACC/AHA categories.
    """
    # 1. PEDIATRIC PATIENT CHECK (< 18 years)
    if patient_age is not None and patient_age < 18.0:
        age_str = int(patient_age) if patient_age.is_integer() else patient_age
        return {
            "classification": "PEDIATRIC_INTERPRETATION_REQUIRED",
            "is_contextual_threshold": True,
            "clinical_source": AAP_SOURCE,
            "contextual_notes": (
                f"Age-Specific Evaluation Required: Patient age is {age_str} years. "
                "Adult ACC/AHA blood pressure benchmarks do not apply to pediatric patients under 18 years of age. "
                "In children and adolescents, blood pressure must be evaluated using age-, sex-, and height-specific percentiles "
                "per AAP guidelines."
            ),
        }

    # 2. HYPERTENSIVE CRISIS CHECK (Acute Urgent Finding)
    if systolic is not None and systolic > 180.0:
        return {
            "classification": "CRITICAL",
            "is_contextual_threshold": True,
            "clinical_source": BP_SOURCE,
            "contextual_notes": (
                "Critical Alert: Systolic blood pressure > 180 mmHg indicates potential hypertensive crisis requiring prompt "
                "clinical evaluation. Complete staging requires concurrent diastolic measurement and medical assessment by a physician."
            ),
        }
    if diastolic is not None and diastolic > 120.0:
        return {
            "classification": "CRITICAL",
            "is_contextual_threshold": True,
            "clinical_source": BP_SOURCE,
            "contextual_notes": (
                "Critical Alert: Diastolic blood pressure > 120 mmHg indicates potential hypertensive crisis requiring immediate "
                "clinical evaluation. Complete staging requires concurrent systolic measurement."
            ),
        }

    # 3. INCOMPLETE ASSESSMENT: DIASTOLIC MEASUREMENT MISSING
    if systolic is not None and diastolic is None:
        sys_str = int(systolic) if systolic.is_integer() else systolic
        if systolic >= 120.0:
            notes = (
                f"Incomplete Blood Pressure Assessment: An isolated systolic reading of {sys_str} mmHg "
                "cannot be assigned a complete blood pressure category without concurrent diastolic blood pressure. "
                "In accordance with the 2017 ACC/AHA High Blood Pressure Clinical Practice Guideline, complete blood pressure evaluation "
                "requires concurrent diastolic measurement and repeated readings taken under standardized clinical conditions. "
                f"While {sys_str} mmHg is above the optimal adult systolic threshold (< 120 mmHg), "
                "an isolated reading does not establish a diagnosis of hypertension. "
                "Note: ACC/AHA benchmarks apply strictly to adults aged 18 and older; pediatric patients require age-specific percentiles."
            )
        else:
            notes = (
                f"Incomplete Blood Pressure Assessment: An isolated systolic reading of {sys_str} mmHg "
                "falls within the optimal adult systolic range (< 120 mmHg), but a complete blood pressure assessment requires "
                "concurrent diastolic measurement and repeated clinical readings per 2017 ACC/AHA guidelines. "
                "Note: ACC/AHA benchmarks apply to adults aged 18 and older."
            )
        return {
            "classification": "INCOMPLETE_ASSESSMENT",
            "is_contextual_threshold": True,
            "clinical_source": BP_SOURCE,
            "contextual_notes": notes,
        }

    # 4. INCOMPLETE ASSESSMENT: SYSTOLIC MEASUREMENT MISSING
    if diastolic is not None and systolic is None:
        dia_str = int(diastolic) if diastolic.is_integer() else diastolic
        if diastolic >= 80.0:
            notes = (
                f"Incomplete Blood Pressure Assessment: An isolated diastolic reading of {dia_str} mmHg "
                "cannot be assigned a complete blood pressure category without concurrent systolic blood pressure. "
                "In accordance with the 2017 ACC/AHA Guideline, complete evaluation requires concurrent systolic measurement "
                "and repeated clinical readings. An isolated reading does not establish a diagnosis of hypertension."
            )
        else:
            notes = (
                f"Incomplete Blood Pressure Assessment: An isolated diastolic reading of {dia_str} mmHg "
                "falls within optimal adult diastolic limits (< 80 mmHg), but complete staging requires concurrent systolic measurement."
            )
        return {
            "classification": "INCOMPLETE_ASSESSMENT",
            "is_contextual_threshold": True,
            "clinical_source": BP_SOURCE,
            "contextual_notes": notes,
        }

    # 5. COMPLETE BLOOD PRESSURE EVALUATION (Both Systolic and Diastolic Available)
    if systolic is not None and diastolic is not None:
        sys_str = int(systolic) if systolic.is_integer() else systolic
        dia_str = int(diastolic) if diastolic.is_integer() else diastolic
        reading_str = f"{sys_str}/{dia_str} mmHg"

        if systolic >= 140.0 or diastolic >= 90.0:
            return {
                "classification": "ABOVE_RANGE",
                "is_contextual_threshold": True,
                "clinical_source": BP_SOURCE,
                "contextual_notes": (
                    f"Complete blood pressure reading is {reading_str}, which falls in the Stage 2 benchmark per 2017 ACC/AHA guidelines. "
                    "CRITICAL SAFETY NOTICE: An isolated single-visit reading does NOT diagnose hypertension. "
                    "Clinical diagnosis requires repeated measurements across multiple occasions by a healthcare provider."
                ),
            }
        elif (130.0 <= systolic < 140.0) or (80.0 <= diastolic < 90.0):
            return {
                "classification": "ABOVE_RANGE",
                "is_contextual_threshold": True,
                "clinical_source": BP_SOURCE,
                "contextual_notes": (
                    f"Complete blood pressure reading is {reading_str}, which falls in the Stage 1 benchmark per 2017 ACC/AHA guidelines. "
                    "Note: An isolated reading cannot diagnose hypertension; repeated clinical measurements on separate occasions by a healthcare provider are required."
                ),
            }
        elif (120.0 <= systolic < 130.0) and diastolic < 80.0:
            return {
                "classification": "ABOVE_RANGE",
                "is_contextual_threshold": True,
                "clinical_source": BP_SOURCE,
                "contextual_notes": (
                    f"Complete blood pressure reading is {reading_str}, reflecting an elevated systolic reading above optimal (< 120 mmHg) "
                    "with normal diastolic (< 80 mmHg) per 2017 ACC/AHA guidelines. "
                    "This is not confirmed hypertension; lifestyle factors and monitoring should be discussed with a doctor."
                ),
            }
        elif (90.0 <= systolic < 120.0) and (60.0 <= diastolic < 80.0):
            return {
                "classification": "WITHIN_RANGE",
                "is_contextual_threshold": not has_lab_range,
                "clinical_source": BP_SOURCE if not has_lab_range else None,
                "contextual_notes": (
                    f"Complete blood pressure reading is {reading_str}, which is within normal adult limits (< 120/< 80 mmHg) "
                    "per 2017 ACC/AHA guidelines."
                ),
            }
        else:  # Hypotension (systolic < 90 or diastolic < 60)
            return {
                "classification": "BELOW_RANGE",
                "is_contextual_threshold": True,
                "clinical_source": BP_SOURCE,
                "contextual_notes": (
                    f"Complete blood pressure reading is {reading_str}, indicating low blood pressure (hypotension). "
                    "Discuss these findings with your healthcare provider."
                ),
            }

    return {
        "classification": "INCOMPLETE_ASSESSMENT",
        "is_contextual_threshold": True,
        "clinical_source": BP_SOURCE,
        "contextual_notes": "Blood pressure value could not be parsed as a complete numerical measurement.",
    }


def classify_parameter(
    param: Dict[str, Any],
    llm_classification: Optional[str] = None,
    all_parameters: Optional[List[Dict[str, Any]]] = None,
    patient_age: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Authoritative classification of a medical parameter.
    
    Enforces strict rules:
    1. Critical flags/thresholds trigger 'CRITICAL'.
    2. Contextual benchmarks (LVEF, Blood Pressure) apply when recognized.
       - LVEF 40% is classified as BELOW_RANGE (ACC/AHA source, non-diagnostic of heart failure).
       - Blood Pressure: Missing diastolic triggers 'INCOMPLETE_ASSESSMENT'.
         Patients under 18 trigger 'PEDIATRIC_INTERPRETATION_REQUIRED'.
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

    # Detect patient age if available
    effective_age = detect_patient_age(param, all_parameters, explicit_age=patient_age)

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

    # 3. Recognized Contextual Benchmark: Blood Pressure (Systolic, Diastolic, or Combined)
    sys_val, dia_val, is_bp = parse_blood_pressure_values(param, all_parameters)
    if is_bp:
        has_lab_range = bool(ref_min is not None or ref_max is not None or ref_text)
        return evaluate_blood_pressure(
            systolic=sys_val,
            diastolic=dia_val,
            patient_age=effective_age,
            has_lab_range=has_lab_range,
        )

    # 4. Laboratory Printed Reference Range Evaluation
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

    # 5. Printed Laboratory Flag without printed numerical range
    if clean_flag in ("H", "HIGH", "ABOVE"):
        return {"classification": "ABOVE_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": "Identified as high by laboratory flag."}
    if clean_flag in ("L", "LOW", "BELOW"):
        return {"classification": "BELOW_RANGE", "is_contextual_threshold": False, "clinical_source": None, "contextual_notes": "Identified as low by laboratory flag."}

    # 6. MISSING REFERENCE RANGE & NO CONTEXTUAL BENCHMARK
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
    patient_age: Optional[float] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Reconciles all parameter explanations and overall summary lists to ensure
    100% mathematical and clinical consistency.
    
    Guarantees:
    - Every parameter card's classification matches its status in overview lists.
    - No parameter is placed in 'parameters_within_range' if its range is missing.
    - Incomplete BP assessments and pediatric BP are placed in 'parameters_unclassified'.
    - LVEF 40% is in 'parameters_outside_range' and never 'parameters_within_range'.
    - Potentially critical flags are 1:1 consistent between overview and parameter cards.
    """
    within_range: List[str] = []
    outside_range: List[str] = []
    unclassified: List[str] = []
    critical_flags: List[str] = []

    # Detect patient age across confirmed parameters if not explicitly provided
    detected_age = detect_patient_age(None, confirmed_parameters, explicit_age=patient_age)

    for param in confirmed_parameters:
        name = param.get("parameter_name", "").strip()
        exp = detailed_explanation.get(name, {})
        llm_cls = exp.get("classification")

        # Compute authoritative classification with full parameter context
        auth_res = classify_parameter(
            param,
            llm_classification=llm_cls,
            all_parameters=confirmed_parameters,
            patient_age=detected_age,
        )
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
        else:  # INCOMPLETE_ASSESSMENT, PEDIATRIC_INTERPRETATION_REQUIRED, RANGE_UNAVAILABLE, NOT_CLASSIFIED, UNKNOWN, UNCONFIRMED_OCR_VALUE
            unclassified.append(name)

    # Reconcile overall summary lists
    # Preserve order and avoid duplicates
    overall_summary["parameters_within_range"] = list(dict.fromkeys(within_range))
    overall_summary["parameters_outside_range"] = list(dict.fromkeys(outside_range))
    overall_summary["parameters_unclassified"] = list(dict.fromkeys(unclassified))
    overall_summary["potentially_critical_flags"] = list(dict.fromkeys(critical_flags))

    return overall_summary, detailed_explanation
