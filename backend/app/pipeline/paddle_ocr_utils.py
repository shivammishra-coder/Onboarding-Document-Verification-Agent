"""
Shared PaddleOCR engine + output-parsing helper, used by both Stage 1
(classification, first-page-only) and Stage 2 (full smart page
extraction). Centralized here so both stages parse PaddleOCR's output
the same correct way - see the note in _parse_paddle_output about why
this matters.
"""
import os
import warnings
from typing import Optional

# Required env var for PaddleOCR >= 3.3
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"

warnings.filterwarnings("ignore", category=UserWarning)

from paddleocr import PaddleOCR  # noqa: E402

# Single shared engine instance - PaddleOCR loads several sub-models at
# import time (detection, recognition, orientation, doc unwarping), so
# this must only happen ONCE per process, not per-call or per-stage.
ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", enable_mkldnn=False)


def parse_paddle_output(ocr_results) -> str:
    """
    Extracts recognized text from PaddleOCR's output, supporting both:
      - PaddleOCR >= 3.x (PP-OCRv6 / PaddleX pipeline): each result is a
        dict-like OCRResult object exposing a 'rec_texts' key (list of
        recognized strings).
      - Legacy PaddleOCR (< 3.x): nested list format
        [[[[box_coords], ('text', confidence)], ...]]

    IMPORTANT: iterating a dict-like OCRResult directly (e.g.
    `for line in ocr_results[0]`) yields its KEYS, not per-line text -
    which silently produces identical garbage output on every image,
    since the key names never change between calls, regardless of what's
    actually in the image. This function checks for 'rec_texts' FIRST
    and only falls back to legacy parsing if it's genuinely absent.
    """
    if not ocr_results:
        return ""

    result = ocr_results[0]
    if result is None:
        return ""

    rec_texts = None
    try:
        rec_texts = result["rec_texts"]
    except (TypeError, KeyError, IndexError):
        rec_texts = getattr(result, "rec_texts", None)

    if rec_texts:
        return " ".join(t for t in rec_texts if t)

    try:
        return " ".join(
            line[1][0] for line in result if line and len(line) > 1 and line[1]
        )
    except (TypeError, IndexError):
        return ""


def run_ocr(image_source) -> str:
    """
    image_source: a file path (str) OR a numpy array (RGB image).
    Returns the recognized text as a single string.
    """
    results = ocr_engine.ocr(image_source)
    return parse_paddle_output(results).strip()