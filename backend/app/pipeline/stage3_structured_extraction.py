"""
STAGE 3 - Structured Extraction

Classification already happened in Stage 1 - this stage TRUSTS the
doc_type it's given and only asks the LLM to extract THAT type's fields.

NEW in this version:
- _normalize_id_fields(): strips ALL whitespace (not just leading/trailing)
  from PAN/Aadhaar/IFSC/account numbers and uppercases them, BEFORE shape
  validation and BEFORE the rule engine ever sees them. Fixes two real
  false-positive classes: (1) an OCR-corrupted bilingual label leaving
  stray characters like "/ " glued onto a date, and (2) two genuinely
  identical account numbers being flagged as a "mismatch" purely because
  one had an internal space and the other didn't.
- _clean_raw_date_string(): strips leading punctuation/slashes left over
  from "Label / लेबल: value"-style bilingual OCR text, so a date that IS
  really parseable doesn't get thrown out just because of a stray prefix
  character none of the format strings could ever match.
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from app.pipeline.ollama_client import build_payload, call_ollama_with_retry, strip_thinking_blocks

# Shape patterns now assume PRE-CLEANED values (all whitespace already
# stripped by _normalize_id_fields) - so aadhaar_number no longer needs to
# tolerate optional spaces, and account_number gets a real check for the
# first time (previously not validated at all).
FIELD_SHAPE_PATTERNS = {
    "pan_number": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "aadhaar_number": re.compile(r"^\d{12}$"),
    "ifsc_code": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
    "account_number": re.compile(r"^\d{6,20}$"),  # bank account lengths vary widely by bank; loose bound
}

ID_LIKE_FIELDS = {"pan_number", "aadhaar_number", "ifsc_code", "account_number"}

DATE_FIELDS = {"dob", "doj", "last_working_day", "gap_start_date", "gap_end_date"}
INTEGER_FIELDS = {"passing_year", "total_points_filled"}
LIST_FIELDS = {"employers", "months_provided"}
BOOLEAN_FIELDS = {
    "has_joining_bonus", "is_ctc_signed", "is_bonus_signed",
    "contains_official_signoff_text", "has_supplementary_or_backlog_text",
}

DATE_FORMATS_TO_TRY = [
    "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y", "%d %B %Y",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%b %d, %Y",
]

DOC_TYPE_FIELDS: Dict[str, list] = {
    "PAN_CARD": ["name", "dob", "pan_number"],
    "AADHAAR_CARD": ["name", "dob", "aadhaar_number"],
    "SELF_DECLARATION_FORM": ["candidate_name", "doj"],
    "PF_FORM_11": ["candidate_name", "account_number", "ifsc_code", "total_points_filled (integer)"],
    "CANCELLED_CHEQUE": ["account_number", "ifsc_code"],
    "RESUME": ["candidate_name", "employers (list of strings - COMPANY/EMPLOYER names only, from a Work Experience/Employment section - NOT schools, colleges, or universities from an Education section)"],
    "UAN_SCREENSHOT": ["employment_history (list of objects: company_name, start_date, end_date)"],
    "OFFER_LETTER_PREVIOUS_ORG": ["company_name", "candidate_name"],
    "PAYSLIP": ["company_name", "months_provided (list of strings)"],
    "RESIGNATION_ACCEPTANCE": ["company_name", "last_working_day", "contains_official_signoff_text (boolean)"],
    "RELIEVING_LETTER": ["company_name", "last_working_day", "contains_official_signoff_text (boolean)"],
    "MARKSHEET": ["qualification_level", "passing_year", "has_supplementary_or_backlog_text (boolean)"],
    "DEGREE_CERTIFICATE": ["qualification_level", "passing_year"],
    "SIGNED_OFFER_LETTER_JADE": ["candidate_name", "grade", "location", "has_joining_bonus (boolean)", "is_ctc_signed (boolean)", "is_bonus_signed (boolean)"],
    "GAP_DECLARATION_FORM": ["gap_start_date", "gap_end_date", "reason_for_gap"],
    "GAP_AFFIDAVIT": ["gap_start_date", "gap_end_date", "reason_for_gap"],
}


async def process_document(
    ocr_text: str, doc_type: str, client: httpx.AsyncClient, original_filename: str = ""
) -> Dict[str, Any]:
    fields = DOC_TYPE_FIELDS.get(doc_type)
    if not fields:
        return {"document_type": doc_type, "extracted_data": {}, "_ocrTextPreview": ocr_text[:500]}

    prompt = _build_extraction_prompt(ocr_text, doc_type, fields, original_filename)
    payload = build_payload(prompt)

    try:
        response = await call_ollama_with_retry(client, payload)
        content = response.json()["choices"][0]["message"]["content"]
        content = strip_thinking_blocks(content)
        parsed_result = json.loads(content)

        normalized_result = {
            "document_type": doc_type,
            "extracted_data": parsed_result.get("extracted_data", parsed_result),
        }

        # NOTE: order matters - normalize ID fields FIRST, so shape
        # validation (next step) checks the cleaned value, not the raw
        # OCR-artifact-laden one.
        result = _normalize_id_fields(normalized_result)
        result = _apply_shape_warnings(result)
        result = _normalize_and_validate_dates(result)
        result = _coerce_integer_fields(result)
        result = _coerce_boolean_fields(result)
        result = _clean_list_fields(result)
        result = _filter_resume_employers(result)   # <-- add this
        result["_ocrTextPreview"] = ocr_text[:500]
        return result

    except httpx.TimeoutException:
        return _build_error_response(doc_type, "Ollama request timed out.")
    except json.JSONDecodeError:
        return _build_error_response(doc_type, "Ollama returned malformed JSON.")
    except Exception as e:
        return _build_error_response(doc_type, f"Unexpected error during extraction: {str(e)}")


def _build_extraction_prompt(ocr_text: str, doc_type: str, fields: list, filename: str) -> str:
    field_list_str = ", ".join(fields)
    resume_warning = ""
    if doc_type == "RESUME":
         resume_warning = (
            "\n6. For 'employers': only include organizations from a Work "
            "Experience/Employment/Professional Experience section. Do NOT "
            "include schools, colleges, or universities listed under an "
            "Education section - those are not employers, even if no "
            "explicit employer section exists at all. If the resume has no "
            "work experience section, employers MUST be an empty list []."
           )
    return f"""You are an expert HR Document data extractor.
This document has ALREADY been classified as: {doc_type}
Extract ONLY the following fields: {field_list_str}

FILENAME HINT: "{filename}"

OCR TEXT:
{ocr_text}

RULES:
1. Reply ONLY with valid JSON: {{"extracted_data": {{...}}}}
2. If a field is not present in the text, set it to null. DO NOT guess or infer.
3. For ANY date field, extract ONLY the date value itself, EXACTLY AS
   PRINTED (e.g. "15-07-1993") - do NOT include surrounding labels,
   separators, or punctuation (e.g. a bilingual "Label / लेबल:" prefix).
   Do not reformat, reorder, or convert the date - normalization happens
   separately.
4. For ID/account numbers, extract the digits/characters only, exactly
   as printed - internal spacing is fine either way, it will be
   normalized separately.
5. Do not include reasoning, explanation, or <think> tags - JSON only.{resume_warning}
"""


def _normalize_id_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Strips ALL whitespace (not just leading/trailing) and uppercases
    PAN/Aadhaar/IFSC/account numbers. Fixes two real bugs seen in
    production: an Aadhaar/PAN "12 34 56" style OCR spacing difference
    causing a false identity mismatch, and a bank account number with an
    internal space being flagged as not matching an otherwise-identical
    number with no space."""
    extracted = result.get("extracted_data", {})
    for field in ID_LIKE_FIELDS:
        if field in extracted and extracted[field]:
            extracted[field] = re.sub(r"\s+", "", str(extracted[field])).upper()
    result["extracted_data"] = extracted
    return result


def _apply_shape_warnings(result: Dict[str, Any]) -> Dict[str, Any]:
    extracted = result.get("extracted_data", {})
    warnings = list(result.get("shape_warnings", []))
    for field_name, pattern in FIELD_SHAPE_PATTERNS.items():
        val = extracted.get(field_name)
        if val and not pattern.match(str(val)):
            warnings.append(f"{field_name} value '{val}' does not match the expected structural format.")
    if warnings:
        result["shape_warnings"] = warnings
    return result

EDUCATION_KEYWORDS = {
    "university", "college", "institute", "school", "academy",
    "polytechnic", "vidyalaya", "vishwavidyalaya",
}

def _filter_resume_employers(result: Dict[str, Any]) -> Dict[str, Any]:
    """Drops any 'employer' entry that's actually an educational
    institution - a common LLM confusion when a resume has no explicit
    Work Experience section (see the 'National University of Technology'
    case). Keeps the entry with a shape_warning instead of silently
    dropping it, so HR can see something WAS filtered out."""
    if result.get("document_type") != "RESUME":
        return result

    extracted = result.get("extracted_data", {})
    employers = extracted.get("employers")
    if not isinstance(employers, list):
        return result

    warnings = list(result.get("shape_warnings", []))
    clean_employers = []
    for e in employers:
        if e and any(kw in str(e).lower() for kw in EDUCATION_KEYWORDS):
            warnings.append(f"employers: dropped '{e}' - looks like an educational institution, not a company")
        else:
            clean_employers.append(e)

    extracted["employers"] = clean_employers
    result["extracted_data"] = extracted
    if warnings:
        result["shape_warnings"] = warnings
    return result
def _clean_raw_date_string(raw: str) -> str:
    """Strips leading/trailing junk characters left over from bilingual
    'Label / लेबल: value' style OCR text, where a stray separator (/, :,
    comma, dash) sometimes ends up glued onto the front of an otherwise
    perfectly parseable date. Does NOT touch the actual date digits."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^[\/\\:,;.\-\s]+", "", cleaned)   # strip leading junk
    cleaned = re.sub(r"[\/\\:,;]+$", "", cleaned).strip()  # strip trailing junk too
    return cleaned


def _normalize_date(raw_value: Optional[str]) -> Optional[str]:
    if not raw_value:
        return None
    raw_value = _clean_raw_date_string(str(raw_value))
    for fmt in DATE_FORMATS_TO_TRY:
        try:
            return datetime.strptime(raw_value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_and_validate_dates(result: Dict[str, Any]) -> Dict[str, Any]:
    extracted = result.get("extracted_data", {})
    warnings = list(result.get("shape_warnings", []))
    for field in DATE_FIELDS:
        if field in extracted and extracted[field]:
            raw = extracted[field]
            normalized = _normalize_date(raw)
            if normalized is None:
                warnings.append(f"{field} value '{raw}' could not be parsed as a valid date - likely OCR error, verify manually")
            else:
                extracted[field] = normalized
    result["extracted_data"] = extracted
    if warnings:
        result["shape_warnings"] = warnings
    return result


def _coerce_integer_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    extracted = result.get("extracted_data", {})
    for field in INTEGER_FIELDS:
        if field in extracted and extracted[field] is not None:
            try:
                extracted[field] = int(extracted[field])
            except (ValueError, TypeError):
                extracted[field] = None
    result["extracted_data"] = extracted
    return result


def _coerce_boolean_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    extracted = result.get("extracted_data", {})
    for field in BOOLEAN_FIELDS:
        if field in extracted and extracted[field] is not None:
            val = extracted[field]
            if isinstance(val, str):
                extracted[field] = val.strip().lower() in ("true", "yes", "1")
    result["extracted_data"] = extracted
    return result


def _clean_list_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    extracted = result.get("extracted_data", {})
    for field in LIST_FIELDS:
        if field in extracted and isinstance(extracted[field], list):
            extracted[field] = [item for item in extracted[field] if item]
    result["extracted_data"] = extracted
    return result


def _build_error_response(doc_type: str, error_msg: str) -> Dict[str, Any]:
    return {"document_type": doc_type, "extracted_data": {}, "error": error_msg}