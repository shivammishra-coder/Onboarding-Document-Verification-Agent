"""
Master Orchestrator - 5 Stage Pipeline

Stage 1: Classification (page 1 only)
Stage 2: Smart page extraction (offer letter -> pages 1,6,7,8,11,12; else -> all pages)
Stage 3: Structured extraction (LLM, using the KNOWN doc_type from Stage 1)
Stage 4: Rule engine
Stage 5: Decision engine
"""
import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.pipeline.ollama_client import get_auth_tuple
from app.pipeline.stage1_document_classification import classify_document
from app.pipeline.stage2_smart_extraction import extract_document_text
from app.pipeline.stage3_structured_extraction import process_document
from app.pipeline.stage4_rule_engine import evaluate_dossier
from app.pipeline.stage7_decision_engine import generate_final_verdict


class OnboardingOrchestrator:
    def __init__(self, candidate_profile: Optional[Dict[str, Any]] = None):
        self.candidate_profile = candidate_profile or {"is_fresher": False}

    async def run_pipeline(self, uploaded_files: List[Dict[str, str]]) -> Dict[str, Any]:
        dossier: Dict[str, Any] = {}
        processing_errors: List[str] = []

        semaphore = asyncio.Semaphore(4)  # caps concurrent Ollama calls + EasyOCR CPU load
        timeout = httpx.Timeout(120.0, connect=15.0)

        async with httpx.AsyncClient(timeout=timeout, auth=get_auth_tuple(), verify=False) as client:

            async def _process_single_file(file_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
                filename = file_info.get("originalName")
                try:
                    async with semaphore:
                        # ---- Stage 1: Classification (page 1 only) ----
                        classification = await classify_document(file_info, client)
                        doc_type = classification["document_type"]

                        if doc_type == "UNKNOWN":
                            return {
                                "document_type": "UNKNOWN",
                                "confidence_score": classification["confidence_score"],
                                "extracted_data": {},
                                "originalName": filename,
                                "storedPath": file_info.get("storedPath"),
                                "warning": "Could not classify this document from its first page.",
                            }

                        # ---- Stage 2: Smart page extraction, driven by doc_type ----
                        extraction = await extract_document_text(file_info, doc_type)

                        if extraction.get("error"):
                            processing_errors.append(f"Page extraction failed for {filename}: {extraction['error']}")
                            return None

                        raw_text = extraction.get("rawText", "")
                        if not raw_text.strip():
                            return {
                                "document_type": doc_type,
                                "confidence_score": classification["confidence_score"],
                                "extracted_data": {},
                                "originalName": filename,
                                "storedPath": file_info.get("storedPath"),
                                "pagesRead": extraction.get("pagesRead", []),
                                "warning": "No text could be extracted from the targeted pages.",
                            }

                        # ---- Stage 3: Structured extraction - doc_type already known ----
                        extracted_doc = await process_document(
                            ocr_text=raw_text, doc_type=doc_type, client=client, original_filename=filename,
                        )
                        extracted_doc["confidence_score"] = classification["confidence_score"]
                        extracted_doc["storedPath"] = file_info.get("storedPath")
                        extracted_doc["originalName"] = filename
                        extracted_doc["pagesRead"] = extraction.get("pagesRead", [])
                        return extracted_doc

                except Exception as e:
                    processing_errors.append(f"Failed processing {filename}: {str(e)}")
                    return None

            tasks = [_process_single_file(f) for f in uploaded_files]
            completed_documents = await asyncio.gather(*tasks)

        # ---- Assemble dossier by classified type ----
        for doc in completed_documents:
            if doc:
                doc_type = doc.get("document_type", "UNKNOWN")
                if doc_type != "UNKNOWN":
                    if doc_type in dossier:
                        if not isinstance(dossier[doc_type], list):
                            dossier[doc_type] = [dossier[doc_type]]
                        dossier[doc_type].append(doc)
                    else:
                        dossier[doc_type] = doc
                else:
                    dossier.setdefault("UNKNOWN", []).append(doc)

        # ---- Stage 4: Rule engine ----
        rule_engine_result = evaluate_dossier(dossier)

        # ---- Stage 5: Decision engine ----
        final_verdict = generate_final_verdict(rule_report=rule_engine_result, processing_errors=processing_errors)

        return {
            "status": final_verdict.get("status"),
            "action_items": final_verdict.get("action_items", []),
            "hr_context_notes": final_verdict.get("hr_context_notes", []),
            "summary": final_verdict.get("summary"),
            "pipeline_metrics": {
                "total_documents_processed": len(uploaded_files),
                "unclassified_documents": len(dossier.get("UNKNOWN", [])),
            },
            "detailed_reports": {
                "step3_rule_engine": rule_engine_result,
                "processing_errors": processing_errors,
            },
            "document_extractions": [doc for doc in completed_documents if doc],
        }