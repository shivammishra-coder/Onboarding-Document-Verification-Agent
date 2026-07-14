"""
STAGE 4 - Rule Engine (production-hardened)

Two categories of checks:

1. GENERALIZED ONE-TO-MANY FIELD CONSISTENCY
   Each logical field (name, dob, doj, account_number, ifsc_code, pan_number, 
   aadhaar_number) has a registered list of (doc_type, field_name) SOURCES. 
   At runtime, every value of that field present anywhere in the dossier is 
   collected. The engine then uses each document as a pivot and compares its 
   value against ALL OTHER documents where that field is present (One-to-Many).
   Any mismatch generates an error showing the pivot document and all the 
   differing documents.

2. STRUCTURAL / BUSINESS-RULE CHECKS
   Mandatory document presence, format validation, signature checks, fresher-vs-lateral 
   branching, and gap-declaration logic.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

MANDATORY_DOC_TYPES = {
    "PAN_CARD", "AADHAAR_CARD", "MARKSHEET", "RESUME",
    "SELF_DECLARATION_FORM", "PF_FORM_11", "CANCELLED_CHEQUE",
    "SIGNED_OFFER_LETTER_JADE",
}


# ---------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------
def _normalize_text(text: Optional[str]) -> str:
    """Lowercase, strip punctuation, sort words - so word order/case/
    minor punctuation differences don't count as a mismatch."""
    if not text:
        return ""
    cleaned = re.sub(r"[^a-z0-9\s]", "", str(text).lower())
    return " ".join(sorted(w for w in cleaned.split() if w))


def _normalize_exact(value: Optional[str]) -> str:
    """For values that must match character-for-character once
    whitespace/case noise is removed - dates, account numbers, IDs, IFSC."""
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value)).upper()


def _calculate_days_between(date_str_1: str, date_str_2: str) -> int:
    try:
        d1 = datetime.strptime(date_str_1, "%Y-%m-%d")
        d2 = datetime.strptime(date_str_2, "%Y-%m-%d")
        return abs((d1 - d2).days)  # Absolute value ensures order doesn't break math
    except (ValueError, TypeError):
        return -9999


# ---------------------------------------------------------------------
# Dossier access helpers
# ---------------------------------------------------------------------
def _get_all_instances(dossier: Dict[str, Any], doc_type: str) -> List[Dict[str, Any]]:
    """
    Returns extracted_data for EVERY uploaded instance of doc_type.
    """
    doc = dossier.get(doc_type)
    if doc is None:
        return []
    entries = doc if isinstance(doc, list) else [doc]
    return [e.get("extracted_data", {}) for e in entries if isinstance(e, dict)]


def _unwrap_doc(dossier: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """
    Returns just the FIRST instance's extracted_data.
    """
    instances = _get_all_instances(dossier, doc_type)
    return instances[0] if instances else {}


# ---------------------------------------------------------------------
# GENERALIZED ONE-TO-MANY FIELD CONSISTENCY ENGINE
# ---------------------------------------------------------------------
FIELD_SOURCES: Dict[str, List[Tuple[str, str]]] = {
    "name": [
        ("PAN_CARD", "name"),
        ("AADHAAR_CARD", "name"),
        ("SELF_DECLARATION_FORM", "candidate_name"),
        ("PF_FORM_11", "candidate_name"),
        ("RESUME", "candidate_name"),
        ("OFFER_LETTER_PREVIOUS_ORG", "candidate_name"),
        ("SIGNED_OFFER_LETTER_JADE", "candidate_name"),
    ],
    "dob": [
        ("PAN_CARD", "dob"),
        ("AADHAAR_CARD", "dob"),
    ],
    "doj": [
        ("SELF_DECLARATION_FORM", "doj"),
    ],
    "account_number": [
        ("PF_FORM_11", "account_number"),
        ("CANCELLED_CHEQUE", "account_number"),
    ],
    "ifsc_code": [
        ("PF_FORM_11", "ifsc_code"),
        ("CANCELLED_CHEQUE", "ifsc_code"),
    ],
    "pan_number": [
        ("PAN_CARD", "pan_number"),
        ("PF_FORM_11", "pan_number"),
    ],
    "aadhaar_number": [
        ("AADHAAR_CARD", "aadhaar_number"),
        ("PF_FORM_11", "aadhaar_number"),
    ]
}

FIELD_NORMALIZERS = {
    "name": _normalize_text,
    "dob": _normalize_exact,
    "doj": _normalize_exact,
    "account_number": _normalize_exact,
    "ifsc_code": _normalize_exact,
    "pan_number": _normalize_exact,
    "aadhaar_number": _normalize_exact,
}


def _collect_field_values(
    dossier: Dict[str, Any],
    sources: List[Tuple[str, str]],
    extra_sources: Optional[List[Tuple[str, Optional[str]]]] = None,
) -> List[Tuple[str, str]]:
    """
    Walks every (doc_type, field_name) source, returning a list of (label, raw_value).
    """
    collected: List[Tuple[str, str]] = []

    for doc_type, field_name in sources:
        for idx, data in enumerate(_get_all_instances(dossier, doc_type)):
            value = data.get(field_name)
            if not value:
                continue
            label = doc_type if idx == 0 else f"{doc_type}#{idx + 1}"
            collected.append((label, str(value)))

    for label, value in extra_sources or []:
        if value:
            collected.append((label, str(value)))

    return collected


def _check_field_consistency(
    dossier: Dict[str, Any],
    field_key: str,
    issues: List[str],
    extra_sources: Optional[List[Tuple[str, Optional[str]]]] = None,
) -> None:
    """
    Performs explicit 1-to-Many comparisons. 
    It treats every document as a pivot and checks its value against all 
    other documents present.
    """
    sources = FIELD_SOURCES.get(field_key, [])
    normalize_fn = FIELD_NORMALIZERS.get(field_key, _normalize_text)

    collected = _collect_field_values(dossier, sources, extra_sources)
    if len(collected) < 2:
        return

    field_display = field_key.replace("_", " ").upper()
    
    # One-to-Many Evaluation
    for i, (pivot_label, pivot_raw) in enumerate(collected):
        mismatches = []
        for j, (target_label, target_raw) in enumerate(collected):
            if i == j:
                continue
            if normalize_fn(pivot_raw) != normalize_fn(target_raw):
                mismatches.append(f"{target_label} ('{target_raw}')")
        
        if mismatches:
            mismatch_str = ", ".join(mismatches)
            issues.append(
                f"{field_display} Mismatch: {pivot_label} ('{pivot_raw}') does not match: {mismatch_str}."
            )


# ---------------------------------------------------------------------
# Employer/company cross-referencing
# ---------------------------------------------------------------------
COMPANY_MENTION_SOURCES: List[Tuple[str, str]] = [
    ("OFFER_LETTER_PREVIOUS_ORG", "company_name"),
    ("PAYSLIP", "company_name"),
    ("RESIGNATION_ACCEPTANCE", "company_name"),
    ("RELIEVING_LETTER", "company_name"),
]

def _check_employer_consistency(dossier: Dict[str, Any], issues: List[str]) -> None:
    resume_instances = _get_all_instances(dossier, "RESUME")
    if not resume_instances:
        return
     
    # FIXED: Added 'or []' to safely handle None values extracted by the LLM
    resume_employers = [
        _normalize_text(e) for r in resume_instances for e in (r.get("employers") or []) if e
    ]
    if not resume_employers:
        return

    for uan_data in _get_all_instances(dossier, "UAN_SCREENSHOT"):
        # FIXED: Added 'or []'
        for entry in (uan_data.get("employment_history") or []):
            company = _normalize_text(entry.get("company_name", ""))
            if company and not any(company in r_emp for r_emp in resume_employers):
                issues.append(
                    f"Resume Validation: Employer '{entry.get('company_name')}' found in UAN "
                    "but missing from Resume."
                )

    for doc_type, field_name in COMPANY_MENTION_SOURCES:
        for idx, data in enumerate(_get_all_instances(dossier, doc_type)):
            company = _normalize_text(data.get(field_name, ""))
            if company and not any(company in r_emp for r_emp in resume_employers):
                label = doc_type if idx == 0 else f"{doc_type}#{idx + 1}"
                issues.append(
                    f"Resume Validation: Employer '{data.get(field_name)}' (from {label}) "
                    "not found in Resume's employer list."
                )


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------
def evaluate_dossier(dossier: Dict[str, Dict[str, Any]], candidate_profile: Dict[str, Any] = None) -> Dict[str, Any]:
    candidate_profile = candidate_profile or {}
    issues: List[str] = []
    pending_documents: List[str] = []
    uploaded_types = set(dossier.keys())

    # =========================================================
    # 1. MANDATORY DOCUMENT CHECK
    # =========================================================
    missing_docs = MANDATORY_DOC_TYPES - uploaded_types
    if missing_docs:
        issues.append(f"Missing mandatory documents: {', '.join(sorted(missing_docs))}")

    # =========================================================
    # 2. GENERALIZED ONE-TO-MANY FIELD CONSISTENCY
    # =========================================================
    _check_field_consistency(
        dossier, "name", issues,
        extra_sources=[("REGISTERED_PROFILE", candidate_profile.get("name"))],
    )
    _check_field_consistency(
        dossier, "dob", issues,
        extra_sources=[("REGISTERED_PROFILE", candidate_profile.get("dob"))],
    )
    _check_field_consistency(
        dossier, "doj", issues,
        extra_sources=[("REGISTERED_PROFILE", candidate_profile.get("doj"))],
    )
    _check_field_consistency(dossier, "account_number", issues)
    _check_field_consistency(dossier, "ifsc_code", issues)
    _check_field_consistency(dossier, "pan_number", issues)
    _check_field_consistency(dossier, "aadhaar_number", issues)

    _check_employer_consistency(dossier, issues)

    # =========================================================
    # 3. FORMAT / COMPLETENESS / SIGNATURE CHECKS 
    # =========================================================
    aadhaar = _unwrap_doc(dossier, "AADHAAR_CARD")
    if aadhaar:
        digits_only = re.sub(r"\D", "", str(aadhaar.get("aadhaar_number", "")))
        if digits_only and len(digits_only) != 12:
            issues.append(f"Invalid Aadhaar format: Must be exactly 12 digits, found {len(digits_only)}.")

    pf_form = _unwrap_doc(dossier, "PF_FORM_11")
    if pf_form:
        points = pf_form.get("total_points_filled")
        if points is not None and points < 11:
            issues.append(f"PF Form 11 Incomplete: Only {points}/11 points filled.")
        if pf_form.get("is_signed") is False:
            issues.append("PF Form 11 appears unsigned.")

    self_dec = _unwrap_doc(dossier, "SELF_DECLARATION_FORM")
    if self_dec and self_dec.get("is_signed") is False:
        issues.append("Self Declaration Form appears unsigned.")

    # =========================================================
    # 4. JADE GLOBAL OFFER LETTER 
    # =========================================================
    jade_offer = _unwrap_doc(dossier, "SIGNED_OFFER_LETTER_JADE")
    if jade_offer:
        if not jade_offer.get("grade") or not jade_offer.get("location"):
            issues.append("Jade Offer Letter missing Grade or Location details.")

    # =========================================================
    # 5. SMART FRESHER DETECTION
    # =========================================================
    resume_instances = _get_all_instances(dossier, "RESUME")
    resume = resume_instances[0] if resume_instances else {}
    resume_employers = resume.get("employers", [])

    uan_present = bool(_get_all_instances(dossier, "UAN_SCREENSHOT"))
    prev_offer_present = bool(_get_all_instances(dossier, "OFFER_LETTER_PREVIOUS_ORG"))
    payslips_present = bool(_get_all_instances(dossier, "PAYSLIP"))
    has_experience_docs = uan_present or prev_offer_present or payslips_present

    marksheet = _unwrap_doc(dossier, "MARKSHEET")
    passing_year = marksheet.get("passing_year")
    date_of_joining = self_dec.get("doj")
    is_fresher = False
    if not resume_employers and not has_experience_docs:
        is_fresher = True
    elif passing_year and date_of_joining and int(passing_year) >= date_of_joining.year:  
        is_fresher = True

# =========================================================
    # 6. PAST EMPLOYMENT CHECKS (Lateral Hires Only)
    # =========================================================
    resignation = _unwrap_doc(dossier, "RESIGNATION_ACCEPTANCE")
    relieving = _unwrap_doc(dossier, "RELIEVING_LETTER")
    self_dec_doj = self_dec.get("doj")
    lwd_date = resignation.get("last_working_day") or relieving.get("last_working_day")

    if not is_fresher:
        if not prev_offer_present:
            issues.append("Previous Organization Offer Letter is missing.")

        all_payslip_months = set()
        for payslip_data in _get_all_instances(dossier, "PAYSLIP"):
            # FIXED: Added 'or []' to safely handle None values
            for month in (payslip_data.get("months_provided") or []):
                if month:
                    all_payslip_months.add(str(month).strip())
        if len(all_payslip_months) < 3:
            issues.append(
                f"Payslip Validation: Expected 3 months leading up to LWD, "
                f"found {len(all_payslip_months)} across all payslip document(s)."
            )

        uan = _unwrap_doc(dossier, "UAN_SCREENSHOT")
        # FIXED: Added 'or []' to safely handle None values
        uan_history = uan.get("employment_history") or []
        if uan_history:
            try:
                uan_history_sorted = sorted(
                    uan_history, key=lambda x: datetime.strptime(x["start_date"], "%Y-%m-%d"), reverse=True
                )
                most_recent_org = uan_history_sorted[0]

                if most_recent_org.get("end_date"):
                    if lwd_date and most_recent_org.get("end_date") != lwd_date:
                        issues.append(
                            "UAN end date for the most recent organization does not match "
                            "the LWD on resignation/relieving docs."
                        )

                for older_org in uan_history_sorted[1:]:
                    if not older_org.get("end_date"):
                        issues.append(
                            f"UAN Validation: Missing end date for past employer "
                            f"'{older_org.get('company_name')}'."
                        )
            except (ValueError, TypeError):
                issues.append("UAN Validation: Invalid date formats found in UAN employment history.")

        if self_dec_doj and lwd_date:
            days_gap = _calculate_days_between(self_dec_doj, lwd_date)
            if days_gap != -9999:
                if days_gap <= 3:
                    if not relieving:
                        pending_documents.append(
                            "Immediate Past Relieving Letter (Marked Pending due to fast transition)"
                        )
                    if not resignation:
                        issues.append(
                            "Fast transition detected: Immediate relieving letter is waived, "
                            "but Resignation Acceptance is missing."
                        )
                else:
                    if not relieving:
                        issues.append(
                            "Standard transition detected: Formal Relieving Letter from most "
                            "recent employer is mandatory."
                        )

    # =========================================================
    # 7. GAP DECLARATION LOGIC (Applies to all)
    # =========================================================
    gap_start_date = lwd_date
    if is_fresher and passing_year:
        gap_start_date = f"{passing_year}-07-01"

    if self_dec_doj and gap_start_date:
        days_gap = _calculate_days_between(self_dec_doj, gap_start_date)
        if days_gap != -9999:
            if days_gap > 180 and "GAP_DECLARATION_FORM" not in uploaded_types:
                issues.append(f"Employment/Education gap of {days_gap} days detected. Gap Declaration Form is missing.")
            if days_gap > 365 and "GAP_AFFIDAVIT" not in uploaded_types:
                issues.append(f"Gap of {days_gap} days detected. Notarized Gap Affidavit on stamp paper is missing.")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "pending_documents": pending_documents,
        "dossier_status": "INCOMPLETE" if missing_docs or issues else "COMPLETE",
    }