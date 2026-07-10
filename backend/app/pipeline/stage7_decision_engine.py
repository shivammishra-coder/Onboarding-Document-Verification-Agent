from typing import Any, Dict, List

def generate_final_verdict(
    rule_report: Dict[str, Any], 
    # ai_report: Dict[str, Any], 
    processing_errors: List[str]
) -> Dict[str, Any]:
    """
    Step 5: The Decision Engine.
    Synthesizes all findings into a final, actionable HR onboarding status.
    """
    # 1. System-Level Errors (OCR failures, corrupt PDFs, timeouts)
    if processing_errors:
        return {
            "status": "SYSTEM_ERROR",
            "summary": "Pipeline encountered file processing errors that prevented full analysis.",
            "action_items": [f"[System Error] {err}" for err in processing_errors],
            "hr_context_notes": []
        }

    action_items = []
    
    # 2. Gather Rule Engine Findings (Missing docs, math/banking mismatches)
    rule_issues = rule_report.get("issues", [])
    if rule_issues:
        action_items.extend([f"[Rule Engine] {issue}" for issue in rule_issues])
        
    pending_docs = rule_report.get("pending_documents", [])
    
    # # 3. Gather AI Semantic Findings (Chronology, name matching, continuity)
    # semantic_report = ai_report.get("semantic_analysis", {})
    # if not semantic_report.get("passed", True):
    #     anomalies = semantic_report.get("anomalies", [])
    #     action_items.extend([f"[AI Semantic Check] {anom}" for anom in anomalies])
        
    # # 4. Gather AI Vision Findings (Signatures, white backgrounds, handwriting)
    # vision_report = ai_report.get("vision_analysis", {})
    # if not vision_report.get("passed", True):
    #     visual_flags = vision_report.get("visual_flags", [])
    #     action_items.extend([f"[AI Vision Check] {flag}" for flag in visual_flags])
        
    # 5. Determine the Final Status
    if action_items:
        # If any system raised a flag, a human must look at it.
        status = "NEEDS_HUMAN_REVIEW"
        summary = f"Dossier flagged for HR review with {len(action_items)} total issues."
    
    elif pending_docs:
        # Everything was perfect, but they are a fast-transition hire who gets to submit the Relieving Letter later.
        status = "PENDING_DOCUMENTS"
        summary = f"Dossier passes all current checks, but waiting on {len(pending_docs)} deferred document(s)."
        action_items.extend([f"[Pending Document] {doc}" for doc in pending_docs])
    
    else:
        # The holy grail: flawless onboarding.
        status = "VERIFIED"
        summary = "Candidate dossier is 100% verified, compliant, and ready for payroll onboarding."

    # Capture the AI's contextual notes (e.g., "TCS resolved to Tata Consultancy Services") 
    # to help HR understand why the AI passed certain things.
    # hr_context_notes = semantic_report.get("notes", [])

    return {
        "status": status,
        "summary": summary,
        "action_items": action_items,
        "hr_context_notes": []    #add later if needed
    }