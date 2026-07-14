import re
from datetime import datetime
from typing import Any, Dict, List

MANDATORY_DOC_TYPES = {
    "PAN_CARD", "AADHAAR_CARD", "MARKSHEET", "RESUME", 
    "SELF_DECLARATION_FORM", "PF_FORM_11", "CANCELLED_CHEQUE", 
    "SIGNED_OFFER_LETTER_JADE"
}

def _normalize_text(text: str) -> str:
    if not text: return ""
    cleaned = re.sub(r"[^a-z0-9\s]", "", str(text).lower())
    return " ".join(sorted(w for w in cleaned.split() if w))

def _calculate_days_between(date_str_1: str, date_str_2: str) -> int:
    try:
        d1 = datetime.strptime(date_str_1, "%Y-%m-%d")
        d2 = datetime.strptime(date_str_2, "%Y-%m-%d")
        return abs((d1 - d2).days)  # Absolute value ensures order doesn't break math
    except (ValueError, TypeError):
        return -9999
# =========================================================
# HELPER MUST BE DEFINED ABOVE evaluate_dossier
# =========================================================
def _unwrap_doc(dossier: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """Safely extracts 'extracted_data', handling lists if multiple files exist."""
    doc = dossier.get(doc_type, {})
    
    # If the orchestrator grouped multiple files into a list, grab the first one
    if isinstance(doc, list):
        if not doc: 
            return {}
        doc = doc[0]  
        
    # Dig into the 'extracted_data' key where the actual fields live
    if isinstance(doc, dict):
        return doc.get("extracted_data", {})
        
    return {}

def evaluate_dossier(dossier: Dict[str, Dict[str, Any]], candidate_profile: Dict[str, Any] = None) -> Dict[str, Any]:
    issues = []
    pending_documents = []
    uploaded_types = set(dossier.keys())
    
    # =========================================================
    # 1. EXTRACT ALL DOCUMENTS FIRST (Order matters!)
    # =========================================================
    pan = _unwrap_doc(dossier, "PAN_CARD")
    aadhaar = _unwrap_doc(dossier, "AADHAAR_CARD")
    resume = _unwrap_doc(dossier, "RESUME")
    uan = _unwrap_doc(dossier, "UAN_SCREENSHOT")
    jade_offer = _unwrap_doc(dossier, "SIGNED_OFFER_LETTER_JADE")
    prev_offer = _unwrap_doc(dossier, "OFFER_LETTER_PREVIOUS_ORG")
    payslips = _unwrap_doc(dossier, "PAYSLIP")
    resignation = _unwrap_doc(dossier, "RESIGNATION_ACCEPTANCE")
    relieving = _unwrap_doc(dossier, "RELIEVING_LETTER")
    self_dec = _unwrap_doc(dossier, "SELF_DECLARATION_FORM")
    cheque = _unwrap_doc(dossier, "CANCELLED_CHEQUE")
    pf_form = _unwrap_doc(dossier, "PF_FORM_11")
    marksheet = _unwrap_doc(dossier, "MARKSHEET")

    # =========================================================
    # 2. SMART FRESHER DETECTION
    # =========================================================
    resume_employers = resume.get("employers", [])
    has_experience_docs = bool(uan or prev_offer or payslips)
    passing_year = marksheet.get("passing_year")
    
    is_fresher = False  # Default assumption; will be overridden by logic below
    
    # Assume fresher if they listed no past employers AND uploaded no experience docs
    if not resume_employers and not has_experience_docs:
        is_fresher = True
    # Or assume fresher if they just graduated this year (e.g., >= 2024)
    elif passing_year and int(passing_year) >= datetime.now().year:
        is_fresher = True

    # =========================================================
    # 3. RUN THE RULE ENGINE LOGIC
    # =========================================================
    # 1. MANDATORY DOCUMENT CHECK (Applies to ALL)
    missing_docs = MANDATORY_DOC_TYPES - uploaded_types
    if missing_docs:
        issues.append(f"Missing mandatory documents: {', '.join(missing_docs)}")

    # ... (The rest of your identity, banking, and gap logic goes here, completely unchanged) ...
    # ==========================================
    # 2. IDENTITY CROSS-VERIFICATION
    # ==========================================
    if pan and aadhaar:
        if _normalize_text(pan.get("name")) != _normalize_text(aadhaar.get("name")):
            issues.append(f"Identity Mismatch: PAN name ('{pan.get('name')}') does not match Aadhaar name ('{aadhaar.get('name')}').")
        
        if pan.get("dob") and aadhaar.get("dob") and (pan.get("dob") != aadhaar.get("dob")):
            issues.append(f"DOB Mismatch: PAN DOB ('{pan.get('dob')}') does not match Aadhaar DOB ('{aadhaar.get('dob')}').")

    if aadhaar:
        digits_only = re.sub(r"\D", "", str(aadhaar.get("aadhaar_number", "")))
        if digits_only and len(digits_only) != 12:
            issues.append(f"Invalid Aadhaar format: Must be exactly 12 digits, found {len(digits_only)}.")

# ==========================================
    # 3. PAYROLL & BANKING CROSS-VERIFICATION
    # ==========================================
    if cheque and pf_form:
        # Check IFSC Code
        cheque_ifsc = str(cheque.get("ifsc_code", "")).upper().strip()
        pf_ifsc = str(pf_form.get("ifsc_code", "")).upper().strip()
        if cheque_ifsc and pf_ifsc and (cheque_ifsc != pf_ifsc):
            issues.append(f"Banking Mismatch: Cheque IFSC ('{cheque_ifsc}') does not match PF Form 11 IFSC ('{pf_ifsc}').")

        # Check Account Number
        cheque_acc = str(cheque.get("account_number", "")).strip()
        pf_acc = str(pf_form.get("account_number", "")).strip()
        if cheque_acc and pf_acc and (cheque_acc != pf_acc):
            issues.append(f"Banking Mismatch: Cheque Account Number ('{cheque_acc}') does not match PF Form 11 ('{pf_acc}').")

    # Check PF Form Completion
    if pf_form:
        points = pf_form.get("total_points_filled")
        if points is not None and points < 11:
            issues.append(f"PF Form 11 Incomplete: Only {points}/11 points filled.")

    # ==========================================
    # 4. JADE GLOBAL OFFER LETTER VERIFICATION
    # ==========================================
    if jade_offer:
        if pan and _normalize_text(pan.get("name")) != _normalize_text(jade_offer.get("candidate_name")):
            issues.append("Jade Offer Letter name does not match PAN identity.")
        
        if not jade_offer.get("grade") or not jade_offer.get("location"):
            issues.append("Jade Offer Letter missing Grade or Location details.")

        
        # if jade_offer.get("has_joining_bonus") and not jade_offer.get("is_bonus_signed"):
        #     issues.append("Jade Offer Letter: Joining bonus page is missing a digital signature.")

    # ==========================================
    # 5. PAST EMPLOYMENT CHECKS (Lateral Hires Only)
    # ==========================================
    jade_doj = self_dec.get("doj")
    lwd_date = resignation.get("last_working_day") or relieving.get("last_working_day")

    if not is_fresher:
        # --- A. RESUME CROSS-VERIFICATION ---
        if resume and uan:
            resume_employers = [_normalize_text(e) for e in resume.get("employers", [])]
            uan_employers = [_normalize_text(e.get("company_name", "")) for e in uan.get("employment_history", [])]
            
            for u_emp in uan_employers:
                if u_emp and not any(u_emp in r_emp for r_emp in resume_employers):
                    issues.append(f"Resume Validation: Employer '{u_emp}' found in UAN but missing from Resume.")

        # --- B. IMMEDIATE PAST EMPLOYMENT ---
        if not prev_offer:
            issues.append("Previous Organization Offer Letter is missing.")
        
        payslip_months = payslips.get("months_provided", [])
        if len(payslip_months) < 3:
            issues.append(f"Payslip Validation: Expected 3 months leading up to LWD, found {len(payslip_months)}.")

        # --- C. UAN HISTORY VERIFICATION ---
        uan_history = uan.get("employment_history", [])
        if uan_history:
            try:
                uan_history.sort(key=lambda x: datetime.strptime(x["start_date"], "%Y-%m-%d"), reverse=True)
                most_recent_org = uan_history[0]
                
                if most_recent_org.get("end_date"):
                    if lwd_date and most_recent_org.get("end_date") != lwd_date:
                        issues.append("UAN end date for the most recent organization does not match the LWD on resignation/relieving docs.")
                
                for older_org in uan_history[1:]:
                    if not older_org.get("end_date"):
                        issues.append(f"UAN Validation: Missing end date for past employer '{older_org.get('company_name')}'.")
                        
            except (ValueError, TypeError):
                issues.append("UAN Validation: Invalid date formats found in UAN employment history.")

        # --- D. FAST TRANSITION & RELIEVING LETTER LOGIC ---
        if jade_doj and lwd_date:
            days_gap = _calculate_days_between(jade_doj, lwd_date)
            
            if days_gap != -9999:
                if days_gap <= 3:
                    if not relieving:
                        pending_documents.append("Immediate Past Relieving Letter (Marked Pending due to fast transition)")
                    if not resignation:
                        issues.append("Fast transition detected: Immediate relieving letter is waived, but Resignation Acceptance is missing.")
                else:
                    if not relieving:
                        issues.append("Standard transition detected: Formal Relieving Letter from most recent employer is mandatory.")

# ==========================================
    # 6. GAP DECLARATION LOGIC (Applies to all)
    # ==========================================
    # For freshers, gap is DOJ - Graduation Date. For Laterals, gap is DOJ - LWD.
    gap_start_date = lwd_date
    
    if is_fresher and passing_year:
        # Approximate gap from July 1st of graduation year using the variable 
        # we already extracted cleanly at the top of the function
        gap_start_date = f"{passing_year}-07-01"

    if jade_doj and gap_start_date:
        days_gap = _calculate_days_between(jade_doj, gap_start_date)
        if days_gap != -9999:
            if days_gap > 180 and "GAP_DECLARATION_FORM" not in uploaded_types:
                issues.append(f"Employment/Education gap of {days_gap} days detected. Gap Declaration Form is missing.")
            if days_gap > 365 and "GAP_AFFIDAVIT" not in uploaded_types:
                issues.append(f"Gap of {days_gap} days detected. Notarized Gap Affidavit on stamp paper is missing.")
                        
    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "pending_documents": pending_documents,
        "dossier_status": "INCOMPLETE" if missing_docs or issues else "COMPLETE"
    }