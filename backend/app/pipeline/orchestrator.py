import os
import asyncio
from typing import List, Dict, Any, Optional

# Import components from your stages
from app.pipeline.stage2_ocr_extraction import extract_text  # Step 1
from app.pipeline.stage3_structured_extraction import process_document  # Step 2
from app.pipeline.stage4_rule_engine import evaluate_dossier  # Step 3
from app.pipeline.stage5_ai_cross_validation import run_ai_cross_validation  # Step 4
from app.pipeline.stage7_decision_engine import generate_final_verdict  # Step 5

class OnboardingOrchestrator:
    def __init__(self, candidate_profile: Optional[Dict[str, Any]] = None):
        """
        candidate_profile can contain metadata like:
        {
            "is_fresher": True/False,
            "expected_doj": "2026-07-07"
        }
        """
        self.candidate_profile = candidate_profile or {"is_fresher": False}

    async def run_pipeline(self, uploaded_files: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        The Master 5-Step Pipeline execution loop.
        uploaded_files: A list of file descriptors, e.g.,
           [{"originalName": "my_pan.jpg", "storedPath": "/data/uploads/file1.jpg"}, ...]
        """
        dossier = {}
        processing_errors = []

        # =========================================================================
        # STEP 1 & STEP 2: PARALLEL OCR EXTRACTION, CLASSIFICATION & STRUCTURED GEN
        # =========================================================================
        # We run these concurrently to maximize throughput and minimize overall wait time.
        async def _process_single_file(file_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
            try:
                # Step 1: Hybrid Fast OCR Extraction (Extracts text or native PDF stream)
                # Note: Run in an executor pool if extract_text blocking operations hit CPU bottlenecks
                ocr_result = extract_text(file_info)
                raw_text = ocr_result.get("rawText", "")
                
                if not raw_text.strip():
                    return {
                        "filename": file_info.get("originalName"),
                        "document_type": "UNKNOWN",
                        "extracted_data": {},
                        "warning": "No text could be extracted from this document."
                    }

                # Step 2: Single-Call Groq Classification and Field Extraction
                extracted_doc = await process_document(
                    ocr_text=raw_text, 
                    original_filename=file_info.get("originalName", "")
                )
                
                # Attach file references for downstream multimodal visual auditing if required
                extracted_doc["storedPath"] = file_info.get("storedPath")
                extracted_doc["originalName"] = file_info.get("originalName")
                return extracted_doc

            except Exception as e:
                processing_errors.append(f"Failed processing {file_info.get('originalName')}: {str(e)}")
                return None

        # Execute extractions concurrently
        tasks = [_process_single_file(f) for f in uploaded_files]
        completed_documents = await asyncio.gather(*tasks)

        # Build the structured onboarding dossier mapped by classified Document Type
        for doc in completed_documents:
            if doc:
                doc_type = doc.get("document_type", "UNKNOWN")
                if doc_type != "UNKNOWN":
                    # If multiple files are uploaded for the same type (e.g. multiple marksheets), 
                    # structured as a list or distinct entries depending on downstream schemas
                    if doc_type in dossier:
                        if not isinstance(dossier[doc_type], list):
                            dossier[doc_type] = [dossier[doc_type]]
                        dossier[doc_type].append(doc)
                    else:
                        dossier[doc_type] = doc
                else:
                    # Collect unknown or failed documents into a temporary bin for auditing
                    if "UNKNOWN" not in dossier:
                        dossier["UNKNOWN"] = []
                    dossier["UNKNOWN"].append(doc)

        # =========================================================================
        # STEP 3: DETERMINISTIC Python RULE ENGINE
        # =========================================================================
        # Executes strict, computational, and formatting cross-validations instantly.
        rule_engine_result = evaluate_dossier(dossier)

        # =========================================================================
        # STEP 4: AI SEMANTIC & VISUAL CROSS-VALIDATION
        # =========================================================================
        # Trigger heavy-duty Llama 3.3/3.2 validation only to resolve structural complex gaps,
        # text continuity, educational chronology, and context reasoning anomalies.
        # ai_validation_result = {}
        # if dossier:
        #     # We pass the full processed dossier and the structural report generated by the rule engine
        #     ai_validation_result = await run_ai_cross_validation(
        #         dossier=dossier, 
        #         rule_engine_report=rule_engine_result,
        #         candidate_profile=self.candidate_profile
        #     )

        # =========================================================================
        # STEP 5: DECISION ENGINE
        # =========================================================================
        # Compiles the mathematical logic and cognitive reasoning outputs into a definitive final verdict.
        final_verdict = generate_final_verdict(
            rule_report=rule_engine_result,
            # ai_report=ai_validation_result,
            processing_errors=processing_errors
        )

        return {
            "status": final_verdict.get("status"),  # PASSED, REJECTED, HUMAN_REVIEW
            # "candidate_id": self.candidate_profile.get("candidate_id"),
            "action_items": final_verdict.get("action_items", []),      # <-- Added this
            "hr_context_notes": final_verdict.get("hr_context_notes", []),  # <-- Added this
            "summary": final_verdict.get("summary"),
            "pipeline_metrics": {
                "total_documents_processed": len(uploaded_files),
                "unclassified_documents": len(dossier.get("UNKNOWN", []))
            },
            "detailed_reports": {
                "step3_rule_engine": rule_engine_result,
                # "step4_ai_validation": ai_validation_result,
                "processing_errors": processing_errors
            },
            "document_extractions": [doc for doc in completed_documents if doc]
        }