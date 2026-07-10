import io
import os
from typing import Dict, Optional, TypedDict

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# IMPORTANT: On Windows, uncomment the line below and point it to your Tesseract install path
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\shivam.mishra_jadegl\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
PDF_RENDER_DPI = 300  # High resolution for accurate OCR

class OcrResult(TypedDict):
    rawText: str
    ocrConfidence: float

def extract_text(file: Dict[str, Optional[str]]) -> OcrResult:
    """
    MASTER ROUTER: Checks file type and sends it to the right extractor.
    file: { "originalName": "...", "storedPath": "..." }
    """
    stored_path = file.get("storedPath")
    original_name = file.get("originalName", "") or ""
    ext = os.path.splitext(original_name)[1].lower()

    if not stored_path or not os.path.exists(stored_path):
        return {"rawText": "", "ocrConfidence": 0.0}

    if ext == ".pdf":
        return _extract_from_pdf(stored_path)
    if ext in IMAGE_EXTS:
        return _extract_from_image(stored_path)

    # Unsupported extension
    return {"rawText": "", "ocrConfidence": 0.0}

def _extract_from_image(path: str) -> OcrResult:
    """Handles raw image uploads (JPG, PNG, etc.)"""
    image = Image.open(path).convert("RGB")
    text = pytesseract.image_to_string(image)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    return {"rawText": text.strip(), "ocrConfidence": _average_confidence(data["conf"])}

def _extract_from_pdf(path: str) -> OcrResult:
    """Handles both digital/text PDFs and scanned PDFs."""
    doc = fitz.open(path)
    page_texts = []
    all_confidences = []

    try:
        # Cap the maximum pages to prevent 100-page PDF bomb attacks
        MAX_PAGES = 25 
        limit = min(len(doc), MAX_PAGES)

        for page_index in range(limit):
            page = doc.load_page(page_index)
            
            # 1. Try native text extraction first! (Instant & 100% accurate)
            native_text = page.get_text("text").strip()
            
            # If we find a decent amount of native text, use it and skip OCR
            if len(native_text) > 50:
                page_texts.append(native_text)
                all_confidences.append(100) # Digital text is 100% confident
                continue
            
            # 2. If no text is found, it's a scanned page. Fall back to OCR.
            pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

            page_text = pytesseract.image_to_string(image)
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

            if page_text.strip():
                page_texts.append(page_text.strip())
            all_confidences.extend(data["conf"])
            
    finally:
        doc.close()

    return {
        "rawText": "\n\n".join(page_texts),
        "ocrConfidence": _average_confidence(all_confidences),
    }

def _average_confidence(conf_values: list) -> float:
    """
    Tesseract's image_to_data returns per-word confidences 0-100, with -1
    for non-text regions. Filter those out, average, normalize to 0.0-1.0.
    """
    valid = [int(c) for c in conf_values if str(c).lstrip("-").isdigit() and int(c) >= 0]
    if not valid:
        return 0.0
    return round((sum(valid) / len(valid)) / 100, 2)