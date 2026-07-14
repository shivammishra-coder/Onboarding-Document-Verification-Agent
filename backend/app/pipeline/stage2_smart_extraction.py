"""
STAGE 2 - Smart Page Extraction

Given the doc_type Stage 1 already classified, decides WHICH pages to
extract full text from:
  - SIGNED_OFFER_LETTER_JADE -> ONLY pages 1, 6, 7, 8, 11, 12
  - everything else          -> ALL pages (capped at MAX_PDF_PAGES)

Uses PaddleOCR (via app.pipeline.paddle_ocr_utils) for scanned pages,
same engine/parsing logic as Stage 1 - kept in one shared module so a
parsing fix in one stage can't silently drift out of sync with the other.
"""
import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pdfplumber

from app.pipeline.paddle_ocr_utils import run_ocr

MAX_PDF_PAGES = 25

# 1-indexed, exactly as specified - converted to 0-indexed when slicing
OFFER_LETTER_TARGET_PAGES_1_INDEXED = [1, 6, 7, 8, 11, 12]


def _extract_text_from_single_pdf_page(page: pdfplumber.page.Page) -> str:
    text = page.extract_text()
    if text and text.strip():
        return text.strip()

    try:
        img_obj = page.to_image(resolution=200).original
        img_array = np.array(img_obj.convert("RGB"))
        return run_ocr(img_array)
    except Exception as e:
        print(f"  [Stage2] Scanned page OCR failed: {e}")
        return ""


def _extract_pages(file_path: str, doc_type: str) -> Tuple[str, List[int], Optional[str]]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext != ".pdf":
        # Single-page image upload - no page-slicing decision to make
        try:
            return run_ocr(file_path), [1], None
        except Exception as e:
            return "", [], f"Image OCR failed: {str(e)}"

    try:
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                return "", [], None

            if doc_type == "SIGNED_OFFER_LETTER_JADE":
                target_indices = [p - 1 for p in OFFER_LETTER_TARGET_PAGES_1_INDEXED]
                pages_to_process = [pdf.pages[i] for i in target_indices if i < total_pages]
                pages_read = [i + 1 for i in target_indices if i < total_pages]
            else:
                pages_to_process = pdf.pages[:MAX_PDF_PAGES]
                pages_read = list(range(1, len(pages_to_process) + 1))

            blocks = [t for t in (_extract_text_from_single_pdf_page(p) for p in pages_to_process) if t]

            return "\n\n--- PAGE BREAK ---\n\n".join(blocks), pages_read, None

    except Exception as e:
        return "", [], f"PDF parse failed: {str(e)}"


async def extract_document_text(file_info: Dict[str, str], doc_type: str) -> Dict[str, Any]:
    """
    file_info: { "originalName": ..., "storedPath": ... }
    doc_type: the type classified in Stage 1 - determines page-slicing strategy
    Returns: { "rawText": str, "pagesRead": [int], "error": Optional[str] }
    """
    file_path = file_info.get("storedPath")
    if not file_path or not os.path.exists(file_path):
        return {"rawText": "", "pagesRead": [], "error": f"File not found: {file_path}"}

    raw_text, pages_read, error = await asyncio.to_thread(_extract_pages, file_path, doc_type)
    return {"rawText": raw_text, "pagesRead": pages_read, "error": error}