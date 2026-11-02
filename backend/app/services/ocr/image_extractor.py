"""
MediExplain AI — OCR Pipeline: Image Extractor
Handles direct image uploads (JPG, PNG) with multi-stage preprocessing,
EXIF orientation correction, contrast enhancement, and Tesseract OCR.
"""
import io
from typing import Optional
from PIL import Image, ImageOps, ImageFilter
import pytesseract


def prepare_image_for_vision(file_bytes: bytes, content_type: str = "image/jpeg") -> tuple[bytes, str]:
    """
    Prepare and optimize an uploaded document image for Gemini Vision:
    1. EXIF orientation correction (phone camera / WhatsApp photos)
    2. RGBA to RGB conversion
    3. Dimensional scaling (max 2560px longest side, min 1000px shortest side)
    4. Adaptive contrast enhancement
    5. Clean JPEG encoding
    Preserves original file_bytes in storage untouched.
    """
    try:
        raw_image = Image.open(io.BytesIO(file_bytes))
        # 1. Correct mobile camera orientation from EXIF
        image = ImageOps.exif_transpose(raw_image)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        # 2. Dimensional normalization
        w, h = image.size
        max_dim = max(w, h)
        min_dim = min(w, h)

        # Scale down if giant (> 2560px)
        if max_dim > 2560:
            scale = 2560.0 / max_dim
            new_size = (int(w * scale), int(h * scale))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        # Scale up if tiny (< 800px)
        elif min_dim < 800:
            scale = 1000.0 / min_dim
            new_size = (int(w * scale), int(h * scale))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        # 3. Dynamic contrast normalization if faint
        enhanced = ImageOps.autocontrast(image, cutoff=1)

        buf = io.BytesIO()
        enhanced.save(buf, format="JPEG", quality=92, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        # Fallback to original bytes and MIME type if processing encounters an issue
        mime = content_type if content_type in ("image/jpeg", "image/png") else "image/jpeg"
        return file_bytes, mime


def extract_text_from_image(file_bytes: bytes, content_type: str = "image/jpeg") -> dict:
    """
    Extract text from an uploaded image file using Tesseract OCR with adaptive preprocessing.

    Returns:
        {
            "text": extracted text string,
            "method": "ocr",
            "confidence": float (0.0 - 1.0),
            "needs_review": bool
        }
    """
    raw_image = Image.open(io.BytesIO(file_bytes))
    
    # 1. Correct mobile camera orientation from EXIF
    image = ImageOps.exif_transpose(raw_image)

    # 2. Standard preprocessing
    processed = _preprocess_image(image)

    # 3. First-pass OCR with word confidences
    try:
        data = pytesseract.image_to_data(
            processed,
            lang="eng",
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )
        confidences = [
            c for c in data["conf"] if isinstance(c, (int, float)) and c != -1
        ]
        avg_confidence = (sum(confidences) / len(confidences) / 100) if confidences else 0.0
        text = pytesseract.image_to_string(processed, lang="eng", config="--psm 6")
    except Exception as e:
        text = ""
        avg_confidence = 0.0

    # 4. If confidence is low or text is sparse, try alternative adaptive binarization pass
    if (avg_confidence < 0.65 or len(text.strip()) < 30) and processed:
        try:
            # High-contrast thresholding for blurry/faint scans
            binarized = processed.point(lambda p: 255 if p > 140 else 0)
            data_alt = pytesseract.image_to_data(
                binarized,
                lang="eng",
                config="--psm 6",
                output_type=pytesseract.Output.DICT,
            )
            alt_confs = [c for c in data_alt["conf"] if isinstance(c, (int, float)) and c != -1]
            alt_avg = (sum(alt_confs) / len(alt_confs) / 100) if alt_confs else 0.0
            alt_text = pytesseract.image_to_string(binarized, lang="eng", config="--psm 6")

            # Choose higher-confidence or more complete extraction
            if alt_avg > avg_confidence or len(alt_text.strip()) > len(text.strip()):
                text = alt_text
                avg_confidence = max(avg_confidence, alt_avg)
        except Exception:
            pass

    clean_text = text.strip()
    needs_review = avg_confidence < 0.70 or not clean_text

    return {
        "text": clean_text,
        "method": "ocr",
        "confidence": round(avg_confidence, 3),
        "needs_review": needs_review,
    }


def _preprocess_image(image: Image.Image) -> Image.Image:
    """
    Multi-stage image preprocessing for noisy or blurry clinical reports:
    1. RGB normalization
    2. Grayscale conversion
    3. Auto-contrast stretching
    4. Unsharp masking for text sharpness
    5. Minimum resolution normalization (min 1200px shortest dimension)
    """
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    gray = image.convert("L")

    # Scale up if image is low-resolution
    min_dim = min(gray.size)
    if min_dim < 1200:
        scale = 1200 / min_dim
        new_size = (int(gray.width * scale), int(gray.height * scale))
        gray = gray.resize(new_size, Image.Resampling.LANCZOS)

    # Dynamic contrast normalization
    gray = ImageOps.autocontrast(gray, cutoff=2)

    # Text edge sharpening
    gray = gray.filter(ImageFilter.SHARPEN)

    return gray
