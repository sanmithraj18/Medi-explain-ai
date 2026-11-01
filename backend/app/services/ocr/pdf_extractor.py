"""
MediExplain AI — OCR Pipeline: PDF Extractor
Uses PyMuPDF for native text extraction, falls back to Tesseract OCR
for scanned pages.
"""
import re
from pathlib import Path
from typing import Optional
import pymupdf as fitz


MIN_TEXT_CHARS_PER_PAGE = 50  # Below this threshold, page is treated as scanned


def extract_text_from_pdf(file_bytes: bytes) -> dict:
    """
    Extract text from a PDF file.
    - Tries native text extraction first (PyMuPDF)
    - Falls back to OCR for pages with insufficient text

    Returns:
        {
            "text": full extracted text,
            "method": "native" | "ocr" | "mixed",
            "pages": int,
            "confidence": float (0.0-1.0),
            "needs_review": bool
        }
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    total_pages = doc.page_count
    all_text = []
    methods_used = set()
    low_confidence_pages = 0

    for page_num in range(total_pages):
        page = doc[page_num]

        # Try native text extraction
        native_text = page.get_text("text").strip()

        if len(native_text) >= MIN_TEXT_CHARS_PER_PAGE:
            all_text.append(native_text)
            methods_used.add("native")
        else:
            # Fall back to OCR for this page
            try:
                ocr_text = _ocr_pdf_page(page)
                if ocr_text:
                    all_text.append(ocr_text)
                    methods_used.add("ocr")
                else:
                    low_confidence_pages += 1
                    all_text.append("")
            except Exception:
                low_confidence_pages += 1
                all_text.append("")

    doc.close()

    full_text = "\n\n".join(filter(None, all_text))

    # Determine overall method and confidence
    if methods_used == {"native"}:
        method = "native"
        confidence = 0.95
    elif methods_used == {"ocr"}:
        method = "ocr"
        confidence = 0.75
    else:
        method = "mixed"
        confidence = 0.80

    # Reduce confidence for pages that failed
    if low_confidence_pages > 0:
        confidence -= (low_confidence_pages / total_pages) * 0.3

    confidence = max(0.0, min(1.0, confidence))
    needs_review = confidence < 0.7

    return {
        "text": full_text,
        "method": method,
        "pages": total_pages,
        "confidence": confidence,
        "needs_review": needs_review,
    }


def _ocr_pdf_page(page: fitz.Page) -> Optional[str]:
    """
    Render a PDF page to an image and run Tesseract OCR on it.
    """
    import pytesseract
    from PIL import Image
    import io

    # Render at 300 DPI for good OCR accuracy
    mat = fitz.Matrix(300 / 72, 300 / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_data = pix.tobytes("png")

    image = Image.open(io.BytesIO(img_data))
    image = _preprocess_image(image)

    text = pytesseract.image_to_string(image, lang="eng", config="--psm 6")
    return text.strip() if text.strip() else None


def _preprocess_image(image) -> "Image":
    """
    Apply basic image preprocessing to improve OCR accuracy.
    """
    from PIL import ImageFilter, ImageOps
    import PIL.Image

    # Convert to grayscale
    if image.mode != "L":
        image = image.convert("L")

    # Increase contrast
    image = ImageOps.autocontrast(image)

    # Mild sharpening
    image = image.filter(ImageFilter.SHARPEN)

    return image

