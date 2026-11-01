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
)
from app.schemas.analysis import OverallSummarySchema, ParameterExplanationSchema

_model = None

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


def _get_model():
    """Lazily initialize the Gemini model using configured settings."""
    global _model
    if _model is None:
        if not settings.AI_API_KEY or settings.AI_API_KEY.strip() == "":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI explanation service is not configured. Please configure AI_API_KEY in backend/.env.",
            )
        genai.configure(api_key=settings.AI_API_KEY)
        _model = genai.GenerativeModel(
            model_name=settings.AI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                temperature=0.1,  # Low temperature for deterministic, factual adherence
                top_p=0.8,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
    return _model


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
    model = _get_model()

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
        response = model.generate_content(prompt)
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
        err_msg = str(e)
        if "quota" in err_msg.lower() or "429" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Gemini AI rate limit reached. Please retry in a few moments.",
            )
        if "timeout" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI explanation service timed out. Please try again.",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {err_msg[:120]}",
        )


async def generate_parameter_explanation(parameter: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate plain-language explanation for a single lab parameter.
    Validates output through ParameterExplanationSchema before returning.
    """
    model = _get_model()

    prompt = PARAMETER_EXPLANATION_PROMPT.format(
        parameter_name=parameter.get("parameter_name", "Unknown"),
        observed_value=str(parameter.get("observed_value", "")),
        unit=parameter.get("unit") or "Not reported",
        reference_text=parameter.get("reference_text") or "Not reported by laboratory",
        lab_flag=parameter.get("laboratory_flag") or "None",
    )

    try:
        response = model.generate_content(prompt)
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
        err_msg = str(e)
        if "quota" in err_msg.lower() or "429" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Gemini AI rate limit reached. Please retry in a few moments.",
            )
        if "timeout" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI explanation service timed out. Please try again.",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {err_msg[:120]}",
        )
