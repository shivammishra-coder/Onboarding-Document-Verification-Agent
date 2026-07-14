"""
STAGE 3 - Vision Structured Extraction

Sends the SELECTED page images (Stage 2) directly to Azure GPT-5 mini and
extracts this doc_type's fields IN ONE CALL - including visual-only
signals (is_signed, is_handwritten, has_watermark_or_stamp) that used to
need a separate vision cross-validation stage. Every normalization
function here (date/ID/boolean cleanup) is carried over unchanged from
the OCR-based version - the extraction SOURCE changed, the guardrails
against a wrong value didn't need to.
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.pipeline.azure_vision_client import build_vision_message, call_vision_with_retry, image_to_data_url

FIELD_SHAPE_PATTERNS = {
    "pan_number": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "aadhaar_number": re.compile(r"^\d{12}$"),
    "ifsc_code": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
    "account_number": re.compile(r"^\d{6,20}$"),
}
ID_LIKE_FIELDS = {"pan_number", "aadhaar_number", "ifsc_code", "account_number"}
DATE_FIELDS = {"dob", "doj", "last_working_day", "gap_start_date", "gap_end_date"}
INTEGER_FIELDS = {"passing_year", "total_points_filled"}
BOOLEAN_FIELDS = {
    "has_joining_bonus", "is_ctc_signed", "is_bonus_signed",
    "contains_official_signoff_text", "has_supplementary_or_backlog_text",
    "is_signed", "is_handwritten", "has_watermark_or_stamp",
}
LIST_FIELDS = {"employers", "months_provided"}
DATE_FORMATS_TO_TRY = [
    "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y", "%d %B %Y",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%b %d, %Y",
]

# Data fields + VISUAL fields (the vision-only additions) per doc type
DOC_TYPE_FIELDS: Dict[str, List[str]] = {
    "PAN_CARD": ["name", "dob", "pan_number"],
    "AADHAAR_CARD": ["name", "dob", "aadhaar_number"],
    "SELF_DECLARATION_FORM": ["candidate_name", "doj", "is_signed (boolean)", "is_handwritten (boolean)"],
    "PF_FORM_11": ["candidate_name", "account_number", "ifsc_code", "total_points_filled (integer)", "is_signed (boolean)", "is_handwritten (boolean)"],
    "CANCELLED_CHEQUE": ["account_number", "ifsc_code"],
    "RESUME": ["candidate_name", "employers (list of COMPANY names ONLY - not schools/universities)"],
    "UAN_SCREENSHOT": ["employment_history (list of objects: company_name, start_date, end_date)"],
    "OFFER_LETTER_PREVIOUS_ORG": ["company_name", "candidate_name"],
    "PAYSLIP": ["company_name", "months_provided (list of strings)"],
    "RESIGNATION_ACCEPTANCE": ["company_name", "last_working_day", "contains_official_signoff_text (boolean)"],
    "RELIEVING_LETTER": ["company_name", "last_working_day", "contains_official_signoff_text (boolean)"],
    "MARKSHEET": ["qualification_level", "passing_year", "has_supplementary_or_backlog_text (boolean)"],
    "DEGREE_CERTIFICATE": ["qualification_level", "passing_year"],
    "SIGNED_OFFER_LETTER_JADE": ["candidate_name", "grade", "location", "has_joining_bonus (boolean)", "is_ctc_signed (boolean)", "is_bonus_signed (boolean)"],
    "GAP_DECLARATION_FORM": ["gap_start_date", "gap_end_date", "reason_for_gap"],
    "GAP_AFFIDAVIT": ["gap_start_date", "gap_end_date", "reason_for_gap", "has_watermark_or_stamp (boolean, notary stamp)"],
}

PROMPT_TEMPLATE = """You are an expert HR document data extractor with vision.
This document has ALREADY been classified as: {doc_type}
You are shown {page_count} page image(s) of it.

Extract ONLY these fields: {field_list}

RULES:
1. Reply ONLY with valid JSON: {{"extracted_data": {{...}}}}
2. If a field is not visible/present, set it to null. DO NOT guess.
3. For date fields, extract EXACTLY AS PRINTED (e.g. "15-07-1993") - do
   not reformat or convert; normalization happens separately.
4. For any boolean field about signatures/handwriting/stamps, judge from
   what you actually SEE - a blank signature line is False, a filled ink
   signature or wet-ink mark is True.
5. Do not include reasoning or extra text - JSON only.
"""


async def process_document(page_images: List[bytes], doc_type: str, filename: str = "") -> Dict[str, Any]:
    fields = DOC_TYPE_FIELDS.get(doc_type)
    if not fields or not page_images:
        return {"document_type": doc_type, "extracted_data": {}}

    prompt = PROMPT_TEMPLATE.format(doc_type=doc_type, page_count=len(page_images), field_list=", ".join(fields))
    image_urls = [image_to_data_url(p) for p in page_images]
    messages = build_vision_message(prompt, image_urls)

    try:
        content = await call_vision_with_retry(messages, response_format={"type": "json_object"})
        parsed = json.loads(content)

        result = {"document_type": doc_type, "extracted_data": parsed.get("extracted_data", parsed)}
        result = _normalize_id_fields(result)
        result = _apply_shape_warnings(result)
        result = _normalize_and_validate_dates(result)
        result = _coerce_integer_fields(result)
        result = _coerce_boolean_fields(result)
        result = _clean_list_fields(result)
        return result
    except Exception as e:
        return {"document_type": doc_type, "extracted_data": {}, "error": f"Vision extraction failed: {str(e)}"}


def _normalize_id_fields(result):
    extracted = result.get("extracted_data", {})
    for f in ID_LIKE_FIELDS:
        if f in extracted and extracted[f]:
            extracted[f] = re.sub(r"\s+", "", str(extracted[f])).upper()
    result["extracted_data"] = extracted
    return result


def _apply_shape_warnings(result):
    extracted = result.get("extracted_data", {})
    warnings = list(result.get("shape_warnings", []))
    for field_name, pattern in FIELD_SHAPE_PATTERNS.items():
        val = extracted.get(field_name)
        if val and not pattern.match(str(val)):
            warnings.append(f"{field_name} value '{val}' does not match expected format.")
    if warnings:
        result["shape_warnings"] = warnings
    return result


def _clean_raw_date_string(raw):
    cleaned = raw.strip()
    cleaned = re.sub(r"^[\/\\:,;.\-\s]+", "", cleaned)
    return re.sub(r"[\/\\:,;]+$", "", cleaned).strip()


def _normalize_date(raw_value):
    if not raw_value:
        return None
    raw_value = _clean_raw_date_string(str(raw_value))
    for fmt in DATE_FORMATS_TO_TRY:
        try:
            return datetime.strptime(raw_value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_and_validate_dates(result):
    extracted = result.get("extracted_data", {})
    warnings = list(result.get("shape_warnings", []))
    for field in DATE_FIELDS:
        if field in extracted and extracted[field]:
            raw = extracted[field]
            normalized = _normalize_date(raw)
            if normalized is None:
                warnings.append(f"{field} value '{raw}' could not be parsed as a valid date.")
            else:
                extracted[field] = normalized
    result["extracted_data"] = extracted
    if warnings:
        result["shape_warnings"] = warnings
    return result


def _coerce_integer_fields(result):
    extracted = result.get("extracted_data", {})
    for f in INTEGER_FIELDS:
        if f in extracted and extracted[f] is not None:
            try:
                extracted[f] = int(extracted[f])
            except (ValueError, TypeError):
                extracted[f] = None
    result["extracted_data"] = extracted
    return result


def _coerce_boolean_fields(result):
    extracted = result.get("extracted_data", {})
    for f in BOOLEAN_FIELDS:
        if f in extracted and extracted[f] is not None:
            val = extracted[f]
            if isinstance(val, str):
                extracted[f] = val.strip().lower() in ("true", "yes", "1")
    result["extracted_data"] = extracted
    return result


def _clean_list_fields(result):
    extracted = result.get("extracted_data", {})
    for f in LIST_FIELDS:
        if f in extracted and isinstance(extracted[f], list):
            extracted[f] = [i for i in extracted[f] if i]
    result["extracted_data"] = extracted
    return result