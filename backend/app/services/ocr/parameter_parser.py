"""
MediExplain AI — OCR Pipeline: Parameter Parser
Parses raw OCR text into structured lab test parameters.

IMPORTANT MEDICAL SAFETY CONSTRAINTS:
1. NEVER invent values, units, or reference ranges. If missing, they remain None.
2. NEVER silently alter ambiguous numbers — flag them for user confirmation.
3. Detect potentially critical physiological findings and flag as CRITICAL with safety guidance.
4. Preserve the laboratory's original reference ranges exactly as reported.
"""
import re
from typing import Optional

# ─── Regex patterns for lab report structure ──────────────────────────────────

# Matches standard lab lines (table columns, colon separated, space separated)
PARAMETER_PATTERN = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 \-\(\)/,\.]{2,50}?)"  # Test name
    r"\s*[:\t| ]\s*"                                     # Separator
    r"(?P<value>[0-9]+(?:[\.,][0-9]+)?)"                # Numeric value
    r"\s*"
    r"(?P<unit>[a-zA-Z/%µ\*][a-zA-Z0-9/%µ\*\.\-\^]*(?:/[a-zA-Z0-9µ\*]+)?)?"  # Unit
    r"\s*"
    r"(?P<ref>(?:[0-9]+\.?[0-9]*\s*[-–—]\s*[0-9]+\.?[0-9]*)"  # Numeric range
    r"|(?:(?:Upto|Up to|Less than|Greater than|>|<|≥|≤)\s*[0-9]+\.?[0-9]*))?",  # Or threshold
    re.IGNORECASE | re.MULTILINE,
)

# Pattern for ambiguous or malformed numbers (e.g. 14..2, 1O.5, commas, OCR artifacts)
AMBIGUOUS_PATTERN = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 \-\(\)/,\.]{2,50}?)"
    r"\s*[:\t| ]\s*"
    r"(?P<value>[0-9A-Za-z]+(?:\.\.[0-9A-Za-z]+|[.,][0-9A-Za-z]+|\b[0-9]+[A-Za-z]+[0-9]*))"
    r"\s*"
    r"(?P<unit>[a-zA-Z/%µ\*][a-zA-Z0-9/%µ\*\.\-\^]*)?"
    r"\s*"
    r"(?P<ref>(?:[0-9]+\.?[0-9]*\s*[-–—]\s*[0-9]+\.?[0-9]*))?",
    re.IGNORECASE | re.MULTILINE,
)

FLAG_PATTERN = re.compile(r"\b(H\*?|L\*?|HH|LL|HIGH|LOW|NORMAL|N|CRITICAL)\b", re.IGNORECASE)

# Known document headers/noise words to ignore as parameter names
SKIP_NAMES = {
    "patient", "name", "age", "sex", "gender", "date", "report", "laboratory",
    "result", "test", "reference", "unit", "range", "method", "sample",
    "collected", "received", "doctor", "hospital", "clinic", "printed", "page",
    "authorised", "authorized", "signature", "dr", "mr", "mrs", "ms",
    "specimen", "investigation", "observed", "interval", "biological",
    "phone", "email", "address", "reg", "barcode", "verified", "status"
}

# Critical physiological thresholds (Safety Guideline)
CRITICAL_THRESHOLDS = [
    (re.compile(r"\b(potassium|serum k)\b", re.I), lambda v: v < 2.8 or v > 6.2),
    (re.compile(r"\b(haemoglobin|hemoglobin|hgb)\b", re.I), lambda v: v < 7.0),
    (re.compile(r"\b(platelet|platelets|plt)\b", re.I), lambda v: (v < 20000 and v > 100) or (v < 20 and v > 0)),
    (re.compile(r"\b(glucose|blood sugar|fasting glucose)\b", re.I), lambda v: v < 50 or v > 400),
    (re.compile(r"\b(sodium|serum na)\b", re.I), lambda v: v < 120 or v > 160),
    (re.compile(r"\b(calcium)\b", re.I), lambda v: v < 6.5 or v > 13.0),
]

MIN_VALUE = 0.0
MAX_VALUE = 999999.0


def parse_parameters(raw_text: str) -> list[dict]:
    """
    Parse raw OCR or digital document text into structured lab test parameters.
    Guarantees medical safety:
    - Never invents ranges or units.
    - Flags ambiguous extractions for user review.
    - Preserves laboratory's original values and reference ranges.
    """
    parameters = []
    seen_names = set()

    for raw_line in raw_text.split("\n"):
        line = raw_line.strip()
        if not line or len(line) < 4:
            continue

        # Skip document headers, page markings (e.g. "PAGE 1", "PAGE - 2")
        if re.search(r"\bpage\s*[-–—:]?\s*\d+\b", line, re.I):
            continue

        # Normalize pipe delimiters from ASCII/markdown tables
        normalized_line = line.replace("|", "  ").strip()

        # Check for ambiguous formatting first (e.g. 1O..2 or 14..2)
        is_ambiguous = False
        match = None
        if re.search(r"[0-9A-Za-z]+(?:\.\.[0-9A-Za-z]+|\b[0-9]+[A-Za-z]+[0-9]*)", normalized_line):
            match = AMBIGUOUS_PATTERN.search(normalized_line)
            if match:
                is_ambiguous = True

        if not match:
            match = PARAMETER_PATTERN.search(normalized_line)

        if not match:
            continue

        name = _clean_name(match.group("name"))
        value_str = match.group("value")
        unit = _clean_unit(match.group("unit"))
        ref_text = _clean_ref(match.group("ref"))

        if not name or not value_str:
            continue
        if name.lower() in SKIP_NAMES or name.lower().endswith("page"):
            continue
        if any(w.lower() in {"page", "patient", "doctor", "specimen", "signature"} for w in name.split()):
            continue
        if name in seen_names:
            continue

        # Parse numeric value if possible
        numeric_value = None
        has_ambiguous_chars = False

        # Check for ambiguous letters in numbers (e.g., 'O' instead of '0')
        if any(c in value_str for c in ("O", "o", "I", "l", "..")):
            has_ambiguous_chars = True
            is_ambiguous = True

        try:
            # Replace comma with period for float conversion check
            numeric_value = float(value_str.replace(",", ".").replace("O", "0").replace("o", "0").replace("I", "1").replace("l", "1"))
            if not (MIN_VALUE <= numeric_value <= MAX_VALUE):
                numeric_value = None
        except ValueError:
            numeric_value = None
            is_ambiguous = True

        # Parse reference range without inventing
        ref_min, ref_max = _parse_reference_range(ref_text)

        # Detect lab flag (H / L / N / CRITICAL)
        lab_flag, safety_alert = _detect_flag_and_safety(
            line=line,
            name=name,
            value=numeric_value,
            ref_min=ref_min,
            ref_max=ref_max,
        )

        # Calculate confidence
        confidence = _calculate_confidence(
            name=name,
            value_str=value_str,
            unit=unit,
            ref_text=ref_text,
            is_ambiguous=is_ambiguous,
            has_ambiguous_chars=has_ambiguous_chars,
        )

        needs_review = is_ambiguous or has_ambiguous_chars or confidence < 0.70

        seen_names.add(name)

        parameters.append({
            "parameter_name": name,
            "observed_value": value_str,  # Original raw value preserved exactly
            "unit": unit,                 # None if not reported
            "reference_min": ref_min,     # None if not reported
            "reference_max": ref_max,     # None if not reported
            "reference_text": ref_text,   # None if not reported
            "laboratory_flag": lab_flag,
            "extraction_confidence": confidence,
            "needs_user_review": needs_review,
            "user_confirmed": False,
            "safety_alert": safety_alert,
        })

    return parameters


def _clean_name(raw: Optional[str]) -> str:
    """Normalise test name — collapse whitespace, remove bullet points/numbers."""
    if not raw:
        return ""
    name = re.sub(r"[:\-|_]+$", "", raw.strip())
    name = re.sub(r"\s{2,}", " ", name)
    name = re.sub(r"^\d+[\.\)]\s*", "", name)
    return name.strip().title()


def _clean_unit(raw: Optional[str]) -> Optional[str]:
    """Clean unit string; return None if empty or invalid."""
    if not raw:
        return None
    cleaned = raw.strip().rstrip(".")
    # Filter noise words that aren't medical units
    if cleaned.lower() in ("high", "low", "normal", "n", "h", "l", "ref", "range"):
        return None
    return cleaned if cleaned else None


def _clean_ref(raw: Optional[str]) -> Optional[str]:
    """Clean reference range text; return None if not present."""
    if not raw:
        return None
    cleaned = raw.strip()
    cleaned = re.sub(r"[–—]", "-", cleaned)
    return cleaned if cleaned else None


def _parse_reference_range(ref_text: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """
    Parse a reference range string into (min, max) floats.
    NEVER invents a range — returns (None, None) if ambiguous or missing.
    """
    if not ref_text:
        return None, None

    # Pattern: "3.5 - 5.5"
    range_match = re.search(r"([0-9]+\.?[0-9]*)\s*[-–—]\s*([0-9]+\.?[0-9]*)", ref_text)
    if range_match:
        try:
            return float(range_match.group(1)), float(range_match.group(2))
        except ValueError:
            return None, None

    # Pattern: "< 200" or "Less than 200"
    upper_match = re.search(r"(?:less than|upto|up to|<|≤)\s*([0-9]+\.?[0-9]*)", ref_text, re.IGNORECASE)
    if upper_match:
        try:
            return None, float(upper_match.group(1))
        except ValueError:
            return None, None

    # Pattern: "> 40" or "Greater than 40"
    lower_match = re.search(r"(?:greater than|>|≥)\s*([0-9]+\.?[0-9]*)", ref_text, re.IGNORECASE)
    if lower_match:
        try:
            return float(lower_match.group(1)), None
        except ValueError:
            return None, None

    return None, None


def _detect_flag_and_safety(
    line: str,
    name: str,
    value: Optional[float],
    ref_min: Optional[float],
    ref_max: Optional[float],
) -> tuple[Optional[str], Optional[str]]:
    """
    Identify laboratory abnormal flags and physiological critical values.
    Returns (flag, safety_alert).
    """
    flag = None
    safety_alert = None

    # 1. Check explicit laboratory flags on the report line
    flag_match = FLAG_PATTERN.search(line)
    if flag_match:
        raw_flag = flag_match.group(0).upper().rstrip("*")
        if raw_flag in ("HIGH", "H", "HH"):
            flag = "H"
        elif raw_flag in ("LOW", "L", "LL"):
            flag = "L"
        elif raw_flag in ("NORMAL", "N"):
            flag = "N"
        elif raw_flag == "CRITICAL":
            flag = "CRITICAL"

    # 2. Derive flag from reference range if not explicitly printed
    if flag is None and value is not None:
        if ref_min is not None and value < ref_min:
            flag = "L"
        elif ref_max is not None and value > ref_max:
            flag = "H"
        elif ref_min is not None and ref_max is not None:
            flag = "N"

    # 3. Medical Safety Check: Potentially Critical Values
    if value is not None:
        for pattern, check_func in CRITICAL_THRESHOLDS:
            if pattern.search(name):
                try:
                    if check_func(value):
                        flag = "CRITICAL"
                        safety_alert = "Critical physiological value observed. Prompt consultation with a healthcare professional is strongly recommended."
                        break
                except Exception:
                    pass

    return flag, safety_alert


def _detect_flag(
    line: str,
    value: Optional[float],
    ref_min: Optional[float],
    ref_max: Optional[float],
) -> Optional[str]:
    """Compatibility wrapper for flag detection without safety context."""
    flag, _ = _detect_flag_and_safety(line, "", value, ref_min, ref_max)
    return flag


def _calculate_confidence(
    name: str,
    value_str: str,
    unit: Optional[str],
    ref_text: Optional[str],
    is_ambiguous: bool = False,
    has_ambiguous_chars: bool = False,
) -> float:
    """
    Calculate confidence score from 0.0 to 1.0 based on structural signals.
    """
    if is_ambiguous or has_ambiguous_chars:
        return 0.45

    score = 0.50

    if len(name) >= 4:
        score += 0.10
    if len(name.split()) >= 2:
        score += 0.05

    # Unit present
    if unit:
        score += 0.15

    # Reference range present
    if ref_text:
        score += 0.15

    # Clean numeric value (no unusual punctuation)
    if re.match(r"^\d+(\.\d+)?$", value_str):
        score += 0.05

    return min(1.0, round(score, 2))
