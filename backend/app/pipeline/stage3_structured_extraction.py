"""
STAGE 3 - Structured Extraction

Root causes fixed here (carried over from the Groq version, still apply):
1. Retry/backoff on 429 and 5xx - a self-hosted service behind a VPN can
   still hit transient failures (cold-start timeouts, brief connection
   drops), so retries stay in place even without Groq's per-minute limits.
2. Date fields are extracted verbatim and normalized/validated in Python -
   an OCR-corrupted "45-07-1993" fails validation instead of being
   silently reformatted into something wrong-but-plausible.
3. Integer fields get explicit type coercion so a malformed value can't
   crash the rule engine downstream.
4. NEW: some models on this endpoint (qwen3:14b, gpt-oss:20b) support a
   "thinking mode" that can prepend <think>...</think> reasoning text
   even when JSON output is requested. That's stripped out before
   json.loads so thinking-mode models don't break parsing.
"""
import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_USERNAME, OLLAMA_PASSWORD, OLLAMA_MODEL

OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 3

FIELD_SHAPE_PATTERNS = {
    "pan_number": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "aadhaar_number": re.compile(r"^\d{4}\s?\d{4}\s?\d{4}$"),
    "ifsc_code": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
}

DATE_FIELDS = {"dob", "doj", "last_working_day", "gap_start_date", "gap_end_date"}
INTEGER_FIELDS = {"passing_year", "total_points_filled"}

#  new code
LIST_FIELDS = {"employers", "months_provided"}  # simple flat lists that shouldn't contain nulls

def _clean_list_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Strips None/empty entries from list-typed fields. The model sometimes
    returns [null] instead of [] when it correctly finds nothing to extract -
    this normalizes that so downstream `if not some_list` checks work as intended."""
    extracted = result.get("extracted_data", {})
    for field in LIST_FIELDS:
        if field in extracted and isinstance(extracted[field], list):
            extracted[field] = [item for item in extracted[field] if item]
    result["extracted_data"] = extracted
    return result

DATE_FORMATS_TO_TRY = [
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%d %B %Y",
    "%d-%b-%Y",    # <-- "01-Aug-2023" - your self-declaration format
    "%d %b %Y",    # "01 Aug 2023" (space instead of dash)
    "%d-%b-%y",    # "01-Aug-23" (2-digit year, in case a document uses it)
    "%b %d, %Y",   # "Aug 01, 2023"
]

THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)

SCHEMA_REFERENCE = (
    "PAN_CARD:[name,dob,pan_number] "
    "AADHAAR_CARD:[name,dob,aadhaar_number] "
    "SELF_DECLARATION_FORM:[candidate_name,doj] "
    "PF_FORM_11:[candidate_name,account_number,ifsc_code,total_points_filled:int] "
    "CANCELLED_CHEQUE:[account_number,ifsc_code] "
    "RESUME:[candidate_name,employers:list[str]] "
    "UAN_SCREENSHOT:[employment_history:list[{company_name,start_date,end_date}]] "
    "SIGNED_OFFER_LETTER_JADE:[candidate_name,grade,location,has_joining_bonus:bool,is_ctc_signed:bool,is_bonus_signed:bool] "
    "PAYSLIP:[company_name,months_provided:list[str]] "
    "RESIGNATION_ACCEPTANCE:[company_name,last_working_day,contains_official_signoff_text:bool] "
    "RELIEVING_LETTER:[company_name,last_working_day,contains_official_signoff_text:bool] "
    "MARKSHEET:[qualification_level,passing_year:str,has_supplementary_or_backlog_text:bool] "
    "DEGREE_CERTIFICATE:[qualification_level,passing_year:str] "
    "OFFER_LETTER_PREVIOUS_ORG:[company_name,candidate_name] "
    "GAP_DECLARATION_FORM:[gap_start_date,gap_end_date,reason_for_gap] "
    "GAP_AFFIDAVIT:[gap_start_date,gap_end_date,reason_for_gap] "
    "UNKNOWN:[]"
)


async def process_document(ocr_text: str, original_filename: str = "") -> Dict[str, Any]:
    if not OLLAMA_USERNAME or not OLLAMA_PASSWORD:
        return _build_error_response("OLLAMA_USERNAME/OLLAMA_PASSWORD are missing. Cannot perform AI extraction.")

    prompt = _build_unified_prompt(ocr_text, original_filename)
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }

    try:
        # Basic Auth per the endpoint guide. 120s timeout covers a cold
        # model load (up to ~8s) plus generation time for our JSON-sized
        # output; bump higher if you switch to gpt-oss:20b under load.
        async with httpx.AsyncClient(auth=(OLLAMA_USERNAME, OLLAMA_PASSWORD), timeout=120.0) as client:
            response = await _call_ollama_with_retry(client, payload)
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            content = _strip_thinking_blocks(content)
            parsed_result = json.loads(content)

            normalized_result = {
                "document_type": parsed_result.get("document_type", "UNKNOWN"),
                "confidence_score": float(parsed_result.get("confidence_score", 0.0)),
                "extracted_data": parsed_result.get("extracted_data", {}),
            }

            result = _apply_shape_warnings(normalized_result)
            result = _normalize_and_validate_dates(result)
            result = _coerce_integer_fields(result)
            result = _clean_list_fields(result)
            result["_ocrTextPreview"] = ocr_text[:500]  # debug aid - tells you OCR vs LLM fault
            return result

    except httpx.TimeoutException:
        return _build_error_response("Ollama request timed out (check VPN/network, or the model may still be cold-starting).")
    except json.JSONDecodeError:
        return _build_error_response("Ollama returned malformed JSON (possibly unstripped thinking-mode output).")
    except Exception as e:
        return _build_error_response(f"Unexpected error during extraction: {str(e)}")


async def _call_ollama_with_retry(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    """
    Retries on 429/5xx and on transient connection errors/timeouts - a
    self-hosted endpoint behind a corporate VPN can occasionally drop a
    connection or take longer than expected on a cold model load, even
    without Groq-style per-minute rate limits.
    """
    last_exception: Optional[Exception] = None
    response: Optional[httpx.Response] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = await client.post(OLLAMA_CHAT_URL, json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as err:
            last_exception = err
            wait_seconds = BASE_BACKOFF_SECONDS * (2 ** attempt)
            print(f"  [connection issue] {err!r} - waiting {wait_seconds:.1f}s (retry {attempt + 1}/{MAX_RETRIES})...")
            await asyncio.sleep(wait_seconds)
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            wait_seconds = float(retry_after) if retry_after else BASE_BACKOFF_SECONDS * (2 ** attempt)
            print(f"  [rate limited] waiting {wait_seconds:.1f}s (retry {attempt + 1}/{MAX_RETRIES})...")
            await asyncio.sleep(wait_seconds)
            continue

        if response.status_code >= 500:
            print(f"  [server error {response.status_code}] waiting before retry {attempt + 1}/{MAX_RETRIES}...")
            await asyncio.sleep(BASE_BACKOFF_SECONDS * (2 ** attempt))
            continue

        response.raise_for_status()
        return response

    if last_exception:
        raise last_exception
    raise httpx.HTTPStatusError(
        f"Ollama API failed after {MAX_RETRIES} retries",
        request=response.request,
        response=response,
    )


def _strip_thinking_blocks(content: str) -> str:
    """
    qwen3:14b and gpt-oss:20b support "thinking mode" and can prepend
    <think>...reasoning...</think> before the actual JSON, even when
    response_format=json_object is requested. Strip it defensively so
    json.loads doesn't choke on it. llama3.1:8b doesn't use this at all,
    so this is a no-op for that model.
    """
    stripped = THINK_BLOCK_PATTERN.sub("", content).strip()
    return stripped if stripped else content


def _build_unified_prompt(ocr_text: str, filename: str) -> str:
    return f"""You are an expert HR Document Analyzer.
Classify the document and extract fields into JSON.

FILENAME HINT: "{filename}"

OCR TEXT:
{ocr_text}

DOCUMENT TYPES & FIELDS: {SCHEMA_REFERENCE}

RULES:
1. Reply ONLY with valid JSON.
2. Pick the single best document_type from the list.
3. Populate extracted_data ONLY with fields required for that type.
4. If a field is not present, set it to null. DO NOT guess or infer.
5. For ANY date field, extract it EXACTLY AS PRINTED on the document
   (e.g. "15-07-1993") - do NOT reformat, reorder, or convert it.
   Date normalization is handled separately, outside this step.
6. confidence_score is a float 0.0-1.0.
7. Do not include any reasoning, explanation, or <think> tags - output
   ONLY the JSON object below.

OUTPUT FORMAT:
{{"document_type": "<Type>", "confidence_score": 0.95, "extracted_data": {{}}}}
"""


def _apply_shape_warnings(result: Dict[str, Any]) -> Dict[str, Any]:
    extracted = result.get("extracted_data", {})
    warnings = []
    for field_name, pattern in FIELD_SHAPE_PATTERNS.items():
        val = extracted.get(field_name)
        if val:
            clean_val = str(val).replace(" ", "").strip() if field_name == "aadhaar_number" else str(val).strip()
            if not pattern.match(clean_val):
                warnings.append(f"{field_name} value '{val}' does not match the expected structural format.")
    if warnings:
        result["shape_warnings"] = warnings
    return result


def _normalize_date(raw_value: Optional[str]) -> Optional[str]:
    """Parses the LLM's verbatim-extracted date string deterministically in
    Python, rather than trusting the LLM's own reformatting. Returns None
    (not a guess) if the string doesn't match any real calendar date -
    e.g. an OCR-corrupted '45-07-1993' correctly fails here."""
    if not raw_value:
        return None
    raw_value = str(raw_value).strip()
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


def _build_error_response(error_msg: str) -> Dict[str, Any]:
    return {"document_type": "UNKNOWN", "confidence_score": 0.0, "extracted_data": {}, "error": error_msg}