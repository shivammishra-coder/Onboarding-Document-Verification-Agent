"""
STAGE 1 - Vision Classification (page 1 image ONLY)

Sends page 1's raw image directly to Azure GPT-5 mini and asks it to
classify the document. The model reads the pixels - no text extraction
step exists to lose information before classification happens.
"""
import json
from typing import Any, Dict

from app.pipeline.azure_vision_client import build_vision_message, call_vision_with_retry, image_to_data_url

VALID_DOC_TYPES = [
    "PAN_CARD", "AADHAAR_CARD", "MARKSHEET", "DEGREE_CERTIFICATE", "RESUME",
    "OFFER_LETTER_PREVIOUS_ORG", "PAYSLIP", "RESIGNATION_ACCEPTANCE",
    "RELIEVING_LETTER", "UAN_SCREENSHOT", "PF_FORM_11", "SELF_DECLARATION_FORM",
    "SIGNED_OFFER_LETTER_JADE", "GAP_DECLARATION_FORM", "GAP_AFFIDAVIT",
    "CANCELLED_CHEQUE", "UNKNOWN",
]

PROMPT_TEMPLATE = """You are a strict HR document classifier with vision.
Look at this image (page 1 of an uploaded document) and classify it.

FILENAME HINT: "{filename}"

VALID DOCUMENT TYPES:
{doc_types}

RULES:
1. Reply ONLY with valid JSON, no markdown, no extra text.
2. Pick the single best matching type.
3. SIGNED_OFFER_LETTER_JADE = any offer letter issued by "Jade Global",
   regardless of whether signature fields are filled in yet.
   OFFER_LETTER_PREVIOUS_ORG = an offer letter from any OTHER company.
4. If nothing matches confidently, return "UNKNOWN".

OUTPUT FORMAT:
{{"document_type": "TYPE_FROM_LIST", "confidence_score": 0.9}}
"""


async def classify_document(first_page_png: bytes, filename: str) -> Dict[str, Any]:
    prompt = PROMPT_TEMPLATE.format(filename=filename, doc_types=json.dumps(VALID_DOC_TYPES))
    messages = build_vision_message(prompt, [image_to_data_url(first_page_png)])

    doc_type, confidence = "UNKNOWN", 0.0
    try:
        content = await call_vision_with_retry(messages, response_format={"type": "json_object"})
        parsed = json.loads(content)
        candidate = str(parsed.get("document_type", "UNKNOWN")).upper().strip()
        doc_type = candidate if candidate in VALID_DOC_TYPES else "UNKNOWN"
        confidence = float(parsed.get("confidence_score", 0.0))
    except Exception as e:
        print(f"  [Stage1] Vision classification failed for {filename}: {e}")

    return {"document_type": doc_type, "confidence_score": confidence}