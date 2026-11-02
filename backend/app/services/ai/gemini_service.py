"""
MediExplain AI — Gemini AI Service
Handles structured medical report explanations with complete safety enforcement.

CREDENTIAL REQUIRED:
  AI_API_KEY — Google AI Studio API key
  Where: backend/.env
  Type: SECRET (server-side only, never expose to frontend)
  Get it: https://aistudio.google.com/app/apikey
"""
import json
import re
from typing import Any, Dict, List

import google.generativeai as genai
from fastapi import HTTPException, status

from app.core.config import settings
from app.services.ai.prompts import (
    SYSTEM_PROMPT,
    OVERALL_SUMMARY_PROMPT,
    PARAMETER_EXPLANATION_PROMPT,
    VISION_EXTRACTION_PROMPT,
)
from app.schemas.analysis import OverallSummarySchema, ParameterExplanationSchema
from app.schemas.extraction import VisionExtractionResponse

_model = None
_active_model_name = None

UNSAFE_DIAGNOSTIC_PATTERNS = [
    re.compile(
        r"\b(you have|diagnosed with|diagnosis is|you suffer from|you are diagnosed with)\s+(diabetes|cancer|anemia|infection|leukemia|disease|syndrome|hypertension|hepatitis|deficiency)\b",
        re.I,
    ),
    re.compile(
        r"\b(take|prescribe|prescribed|dosage of|start taking|stop taking|increase dose|decrease dose)\s+[0-9]*\s*(mg|tablets|capsules|pills|medication|insulin|metformin|aspirin)?\b",
        re.I,
    ),
    re.compile(
        r"\b(you definitely have|this confirms you have|you are suffering from)\b",
        re.I,
    ),
]


def sanitize_and_verify_medical_safety(text: str) -> str:
    """
    Defense-in-depth safety guardrail:
    Scans AI text for diagnostic or prescriptive statements and neutralizes them.
    """
    if not text:
        return ""
    sanitized = text
    for pattern in UNSAFE_DIAGNOSTIC_PATTERNS:
        if pattern.search(sanitized):
            sanitized = pattern.sub(
                "an abnormal laboratory finding warrants clinical evaluation by a physician",
                sanitized,
            )
    return sanitized


DEPRECATED_MODELS = {
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
}
RECOMMENDED_MODEL = "gemini-3.8-flash"


def _create_model(model_name: str):
    """Instantiate a configured Gemini GenerativeModel instance."""
    genai.configure(api_key=settings.AI_API_KEY)
    return genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.1,  # Low temperature for deterministic, factual adherence
            top_p=0.8,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )


def _get_model(model_name: str = None):
    """Lazily initialize the Gemini model using configured settings."""
    global _model, _active_model_name
    if not settings.AI_API_KEY or settings.AI_API_KEY.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI explanation service is not configured. Please configure AI_API_KEY in backend/.env.",
        )

    target = model_name or settings.AI_MODEL or RECOMMENDED_MODEL
    # Auto-upgrade deprecated or retired models to the currently active flash model
    if target in DEPRECATED_MODELS:
        target = RECOMMENDED_MODEL

    if _model is None or _active_model_name != target:
        _model = _create_model(target)
        _active_model_name = target
    return _model


def _generate_content_with_resilience(contents: Any):
    """
    Generate content with primary configured model and automatic fallback on 503/504/404/429 errors.
    Supports text prompt strings or multimodal contents list ([prompt, image_part]).
    Guarded by request timeout to prevent hanging requests during upstream load spikes.
    """
    primary = settings.AI_MODEL or RECOMMENDED_MODEL
    chain = [primary]
    for alt in (
        RECOMMENDED_MODEL,
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    ):
        if alt not in chain:
            chain.append(alt)

    last_exc = None
    for m_name in chain:
        try:
            model = _get_model(m_name)
            return model.generate_content(contents, request_options={"timeout": 20})
        except HTTPException:
            raise
        except Exception as e:
            last_exc = e
            err_str = str(e)
            # If model encounters temporary high demand (503), timeout (504), 404, or model quota limits (429), try next candidate
            if any(k in err_str.lower() for k in ["404", "not found", "503", "unavailable", "high demand", "deadline", "timeout", "quota", "resource_exhausted", "429"]):
                continue
            _handle_gemini_exception(e, m_name)
    _handle_gemini_exception(last_exc, primary)


def _handle_gemini_exception(e: Exception, model_name: str = None):
    """
    Distinctly categorize and raise appropriate HTTP exceptions for Gemini API failures:
    - 404: Model not found / deprecated
    - 503: Invalid/missing API key or service unavailable
    - 429: Rate limit / quota exceeded
    - 504: Request timeout
    """
    if isinstance(e, HTTPException):
        raise e

    err_msg = str(e)
    err_lower = err_msg.lower()
    used_model = model_name or settings.AI_MODEL or "configured model"

    # 1. Model Not Found / Unsupported (404)
    if "404" in err_msg or "not found" in err_lower or "no longer available" in err_lower or "not supported" in err_lower:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gemini model '{used_model}' is not found or no longer supported. Please update AI_MODEL.",
        )

    # 2. Invalid Key / Authentication Error (400, 401, 403, API_KEY_INVALID)
    if "api_key_invalid" in err_lower or "api key not valid" in err_lower or "unauthorized" in err_lower or "permission_denied" in err_lower:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Gemini API key is invalid or unauthorized. Please verify AI_API_KEY.",
        )

    # 3. Rate Limit / Quota Exceeded (429, RESOURCE_EXHAUSTED)
    if "quota" in err_lower or "429" in err_msg or "resource_exhausted" in err_lower:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Gemini AI rate limit reached. Please retry in a few moments.",
        )

    # 4. Timeout / Gateway Timeout (504, DEADLINE_EXCEEDED)
    if "timeout" in err_lower or "deadline_exceeded" in err_lower or "timed out" in err_lower:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI explanation service timed out. Please try again.",
        )

    # 5. Service Overloaded / Unavailable (503)
    if "503" in err_msg or "unavailable" in err_lower or "high demand" in err_lower:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Gemini service is temporarily experiencing high demand. Please retry shortly.",
        )

    # Generic AI Service Error
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"AI service error: {err_msg[:120]}",
    )


def _extract_json(text: str) -> dict:
    """
    Safely extract a JSON object from the model's response.
    Raises ValueError if no valid JSON can be parsed.
    """
    # 1. Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. Try markdown code block extraction
    pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(pattern, text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Try finding outermost JSON curly braces
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        try:
            return json.loads(obj_match.group(0).strip())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from AI response: {text[:200]}")


async def generate_overall_summary(parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate an educational overall summary of all confirmed extracted parameters.
    Validates output through OverallSummarySchema before returning.
    """
    # Pre-check API configuration
    _get_model()

    # Pass strictly extracted facts — NEVER send patient PII
    param_summary = []
    for p in parameters:
        param_summary.append({
            "parameter_name": p.get("parameter_name", "Unknown"),
            "observed_value": str(p.get("observed_value", "")),
            "unit": p.get("unit") or "Not reported by lab",
            "reference_range": p.get("reference_text") or "Not reported by lab",
            "laboratory_flag": p.get("laboratory_flag") or "None",
        })

    prompt = OVERALL_SUMMARY_PROMPT.format(
        parameters_json=json.dumps(param_summary, indent=2)
    )

    try:
        response = _generate_content_with_resilience(prompt)
        raw_result = _extract_json(response.text)

        # Validate with Pydantic schema
        validated = OverallSummarySchema.model_validate(raw_result)
        result_dict = validated.model_dump()

        # Enforce safety guardrails on output text
        result_dict["overall_assessment"] = sanitize_and_verify_medical_safety(
            result_dict.get("overall_assessment", "")
        )
        return result_dict

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI summary response parsing failed: {e}",
        )
    except Exception as e:
        _handle_gemini_exception(e)


async def generate_parameter_explanation(parameter: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate plain-language explanation for a single lab parameter.
    Validates output through ParameterExplanationSchema before returning.
    """
    # Pre-check API configuration
    _get_model()

    prompt = PARAMETER_EXPLANATION_PROMPT.format(
        parameter_name=parameter.get("parameter_name", "Unknown"),
        observed_value=str(parameter.get("observed_value", "")),
        unit=parameter.get("unit") or "Not reported",
        reference_text=parameter.get("reference_text") or "Not reported by laboratory",
        lab_flag=parameter.get("laboratory_flag") or "None",
    )

    try:
        response = _generate_content_with_resilience(prompt)
        raw_result = _extract_json(response.text)

        # Validate with Pydantic schema
        validated = ParameterExplanationSchema.model_validate(raw_result)
        result_dict = validated.model_dump()

        # Enforce safety guardrails
        result_dict["simple_explanation"] = sanitize_and_verify_medical_safety(
            result_dict.get("simple_explanation", "")
        )
        result_dict["what_it_measures"] = sanitize_and_verify_medical_safety(
            result_dict.get("what_it_measures", "")
        )

        return result_dict

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI parameter response parsing failed: {e}",
        )
    except Exception as e:
        _handle_gemini_exception(e)


def _parse_ref_bounds(ref_text: str | None) -> tuple[float | None, float | None]:
    """Extract numeric lower and upper bounds from a printed reference interval string."""
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


def _detect_critical_flag(parameter_name: str, observed_value: str, current_flag: str | None) -> str | None:
    """Detect potentially critical physiological values based on clinical thresholds."""
    if current_flag and "critical" in current_flag.lower():
        return "CRITICAL"
    try:
        num_match = re.search(r"[0-9]+(?:\.[0-9]+)?", observed_value)
        if not num_match:
            return current_flag
        val = float(num_match.group(0))
        from app.services.ocr.parameter_parser import CRITICAL_THRESHOLDS
        for pattern, is_critical in CRITICAL_THRESHOLDS:
            if pattern.search(parameter_name):
                if is_critical(val):
                    return "CRITICAL"
    except Exception:
        pass
    return current_flag


async def extract_parameters_with_vision(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Extract laboratory parameters directly from medical report document image using Gemini Vision.
    Enforces strict truth discovery and schema validation:
    - Never invents parameters, observed values, units, or reference ranges.
    - Accurately captures report title, date, and transcribed raw text.
    - Flags ambiguous, blurry, or low-confidence values for user confirmation.
    """
    _get_model()
    image_part = {"mime_type": mime_type, "data": image_bytes}
    contents = [VISION_EXTRACTION_PROMPT, image_part]

    try:
        response = _generate_content_with_resilience(contents)
        raw_result = _extract_json(response.text)
        validated = VisionExtractionResponse.model_validate(raw_result)

        params_out = []
        for p in validated.parameters:
            name = p.parameter_name.strip()
            val = p.observed_value.strip()
            unit = p.unit.strip() if p.unit else None
            ref_text = p.reference_range.strip() if p.reference_range else None
            ref_min = p.reference_min
            ref_max = p.reference_max
            if ref_text and (ref_min is None and ref_max is None):
                ref_min, ref_max = _parse_ref_bounds(ref_text)

            flag = _detect_critical_flag(name, val, p.laboratory_flag)
            confidence = round(float(p.extraction_confidence), 3)
            needs_review = p.needs_user_review or confidence < 0.70

            params_out.append({
                "parameter_name": name,
                "observed_value": val,
                "unit": unit,
                "reference_min": ref_min,
                "reference_max": ref_max,
                "reference_text": ref_text,
                "laboratory_flag": flag,
                "extraction_confidence": confidence,
                "needs_user_review": needs_review,
                "user_confirmed": False,
            })

        return {
            "report_type": validated.report_type,
            "report_date": validated.report_date,
            "raw_text": validated.raw_text or "",
            "parameters": params_out,
            "extraction_method": "gemini_vision",
            "notes": validated.extraction_notes,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse Gemini vision extraction response: {e}",
        )
    except Exception as e:
        _handle_gemini_exception(e)

