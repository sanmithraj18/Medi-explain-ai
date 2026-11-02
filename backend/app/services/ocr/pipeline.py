"""
MediExplain AI — Unified Document Extraction Pipeline.
Orchestrates multi-engine extraction:
1. Fast local extraction (PyMuPDF native text for digital PDFs, Tesseract OCR for clean images)
2. Robust AI Vision fallback (Gemini Vision with multimodal structured JSON)
3. Medical safety: zero fabrication, strict parameter validation, review flagging
"""
import logging
from typing import Dict, Any, List

from app.services.ocr.pdf_extractor import extract_text_from_pdf, render_pdf_to_images
from app.services.ocr.image_extractor import extract_text_from_image, prepare_image_for_vision
from app.services.ocr.parameter_parser import parse_parameters
from app.services.ai.gemini_service import extract_parameters_with_vision

logger = logging.getLogger(__name__)


async def process_document_extraction(
    file_bytes: bytes,
    file_ext: str,
    content_type: str = "",
) -> Dict[str, Any]:
    """
    Execute end-to-end document extraction across PDF and Image formats.
    Follows multi-stage extraction strategy:
    1. Try native PDF text extraction or local OCR
    2. If extraction produces zero parameters or low confidence, trigger Gemini Vision
    3. Validate and flag ambiguous parameters for user review
    4. Never silently claim success when zero parameters are found
    """
    clean_ext = file_ext.lower().replace(".", "")
    parameters: List[Dict[str, Any]] = []
    raw_text = ""
    report_type = None
    report_date = None
    method_used = "unknown"
    confidence = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # 1. PDF Documents
    # ──────────────────────────────────────────────────────────────────────────
    if clean_ext == "pdf":
        try:
            pdf_res = extract_text_from_pdf(file_bytes)
            raw_text = pdf_res.get("text", "")
            method_used = pdf_res.get("method", "native")
            confidence = pdf_res.get("confidence", 0.0)

            if raw_text and len(raw_text.strip()) >= 30:
                parameters = parse_parameters(raw_text)
        except Exception as e:
            logger.warning(f"Native PDF extraction failed: {e}")

        # If native PDF extraction produced no parameters or low confidence, fallback to Gemini Vision
        if not parameters or confidence < 0.70:
            try:
                page_images = render_pdf_to_images(file_bytes, max_pages=3)
                for page_img in page_images:
                    vision_res = await extract_parameters_with_vision(page_img, "image/png")
                    page_params = vision_res.get("parameters", [])
                    if page_params:
                        # Append parameters from this page
                        parameters.extend(page_params)
                        if not report_type and vision_res.get("report_type"):
                            report_type = vision_res.get("report_type")
                        if not report_date and vision_res.get("report_date"):
                            report_date = vision_res.get("report_date")
                        if vision_res.get("raw_text"):
                            raw_text = (raw_text + "\n\n" + vision_res["raw_text"]).strip()

                if parameters:
                    method_used = "gemini_vision_pdf"
                    confidence = sum(p.get("extraction_confidence", 0.9) for p in parameters) / len(parameters)
            except Exception as e:
                logger.warning(f"Gemini vision PDF fallback failed: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Image Documents (JPG, JPEG, PNG)
    # ──────────────────────────────────────────────────────────────────────────
    else:
        # Step A: Preprocess image for maximum clarity
        vision_bytes, mime = prepare_image_for_vision(file_bytes, content_type)

        # Step B: Attempt local OCR first
        try:
            ocr_res = extract_text_from_image(file_bytes, content_type)
            ocr_text = ocr_res.get("text", "")
            ocr_conf = ocr_res.get("confidence", 0.0)
            if ocr_text:
                ocr_params = parse_parameters(ocr_text)
                if ocr_params and ocr_conf >= 0.80:
                    parameters = ocr_params
                    raw_text = ocr_text
                    method_used = "tesseract_ocr"
                    confidence = ocr_conf
        except Exception as e:
            logger.warning(f"Local OCR attempt failed or Tesseract unavailable: {e}")

        # Step C: If local OCR produced zero parameters or low confidence, trigger Gemini Vision
        if not parameters:
            try:
                vision_res = await extract_parameters_with_vision(vision_bytes, mime)
                vision_params = vision_res.get("parameters", [])
                if vision_params:
                    parameters = vision_params
                    raw_text = vision_res.get("raw_text") or raw_text
                    report_type = vision_res.get("report_type")
                    report_date = vision_res.get("report_date")
                    method_used = "gemini_vision"
                    confidence = sum(p.get("extraction_confidence", 0.9) for p in parameters) / len(parameters)
            except Exception as e:
                logger.warning(f"Gemini vision extraction failed: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Status Evaluation & Medical Review Flagging
    # ──────────────────────────────────────────────────────────────────────────
    if not parameters:
        processing_status = "NEEDS_REVIEW"
        needs_review = True
        message = (
            "Document processed, but no laboratory test parameters could be detected automatically. "
            "The image may be blurry, cropped, or not a diagnostic laboratory report. "
            "You can retry with AI vision or upload a clearer document."
        )
    else:
        # Flag document for review if any parameter is low-confidence or ambiguous
        needs_review = any(p.get("needs_user_review") or p.get("extraction_confidence", 1.0) < 0.70 for p in parameters)
        processing_status = "NEEDS_REVIEW" if needs_review else "EXTRACTED"
        message = (
            f"Successfully extracted {len(parameters)} laboratory parameter(s) from document."
            if not needs_review
            else f"Extracted {len(parameters)} parameter(s). Some values may warrant patient review."
        )

    return {
        "parameters": parameters,
        "processing_status": processing_status,
        "raw_text": raw_text.strip(),
        "extraction_method": method_used,
        "report_type": report_type,
        "report_date": report_date,
        "confidence": round(confidence, 3),
        "needs_review": needs_review,
        "message": message,
    }
