"""
STAGE 1 - Document Classification (first page ONLY)

Extracts text from just page 1 (digital layer, or OCR fallback if page 1
is a scan), then asks the LLM to classify the whole document from that
sample alone. This is deliberately cheap and fast - full-document text
extraction happens in Stage 2, only AFTER we know which pages we need.

Uses the SHARED PaddleOCR engine + output parser from
app.pipeline.paddle_ocr_utils - the same instance/logic Stage 2 uses -
so there's only one engine loaded in memory and only one place that
knows how to parse PaddleOCR's output correctly.
"""
import asyncio
import json
import os
import warnings
from typing import Any, Dict

import numpy as np
import httpx
import pdfplumber

from app.pipeline.ollama_client import build_payload, call_ollama_with_retry, strip_thinking_blocks
from app.pipeline.paddle_ocr_utils import run_ocr

warnings.filterwarnings("ignore", category=UserWarning)

VALID_DOC_TYPES = [
    "PAN_CARD", "AADHAAR_CARD", "MARKSHEET", "DEGREE_CERTIFICATE", "RESUME",
    "OFFER_LETTER_PREVIOUS_ORG", "PAYSLIP", "RESIGNATION_ACCEPTANCE",
    "RELIEVING_LETTER", "UAN_SCREENSHOT", "PF_FORM_11", "SELF_DECLARATION_FORM",
    "SIGNED_OFFER_LETTER_JADE", "GAP_DECLARATION_FORM", "GAP_AFFIDAVIT",
    "CANCELLED_CHEQUE", "UNKNOWN",
]


def _extract_first_page_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        try:
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return ""
                page = pdf.pages[0]
                text = page.extract_text()
                if text and text.strip():
                    return text.strip()

                # Page 1 is a scan - OCR fallback (shared engine)
                img_obj = page.to_image(resolution=200).original
                img_array = np.array(img_obj.convert("RGB"))
                return run_ocr(img_array)

        except Exception as e:
            print(f"  [Stage1] pdfplumber/OCR fallback failed for {file_path}: {e}")
            return ""

    # Native image upload - the whole image IS "page 1"
    try:
        return run_ocr(file_path)
    except Exception as e:
        print(f"  [Stage1] PaddleOCR failed for {file_path}: {e}")
        return ""


def _build_classification_prompt(sample_text: str, filename: str) -> str:
    return f"""You are a strict HR Document Classifier.
Classify this document using ONLY the text from its first page.

FILENAME HINT: "{filename}"

TEXT FROM PAGE 1:
\"\"\"
{sample_text[:1500]}
\"\"\"

VALID DOCUMENT TYPES:
{json.dumps(VALID_DOC_TYPES)}

RULES:
1. Reply ONLY with valid JSON, no markdown, no explanation outside the JSON.
2. Pick the single best matching type from the list above.
3. SIGNED_OFFER_LETTER_JADE = any offer letter issued by "Jade Global" to
   the candidate, regardless of whether signature fields are filled in
   yet. OFFER_LETTER_PREVIOUS_ORG = an offer letter from any OTHER
   (non-Jade) company.
4. If nothing matches confidently, return "UNKNOWN".

OUTPUT FORMAT:
{{"document_type": "TYPE_FROM_LIST", "confidence_score": 0.9}}
"""


async def classify_document(file_info: Dict[str, str], client: httpx.AsyncClient) -> Dict[str, Any]:
    """
    file_info: { "originalName": ..., "storedPath": ... }
    Returns: { "document_type": str, "confidence_score": float, "firstPageTextPreview": str }
    """
    file_path = file_info.get("storedPath")
    filename = file_info.get("originalName") or os.path.basename(file_path or "")

    if not file_path or not os.path.exists(file_path):
        return {"document_type": "UNKNOWN", "confidence_score": 0.0, "firstPageTextPreview": ""}

    first_page_text = await asyncio.to_thread(_extract_first_page_text, file_path)
    if not first_page_text.strip():
        return {"document_type": "UNKNOWN", "confidence_score": 0.0, "firstPageTextPreview": ""}

    prompt = _build_classification_prompt(first_page_text, filename)
    payload = build_payload(prompt)

    doc_type, confidence = "UNKNOWN", 0.0
    try:
        response = await call_ollama_with_retry(client, payload)
        content = response.json()["choices"][0]["message"]["content"]
        content = strip_thinking_blocks(content)
        parsed = json.loads(content)
        candidate_type = str(parsed.get("document_type", "UNKNOWN")).upper().strip()
        doc_type = candidate_type if candidate_type in VALID_DOC_TYPES else "UNKNOWN"
        confidence = float(parsed.get("confidence_score", 0.0))
    except Exception as e:
        print(f"  [Stage1] Classification failed for {filename}: {e}")

    return {
        "document_type": doc_type,
        "confidence_score": confidence,
        "firstPageTextPreview": first_page_text[:300],
    }