"""
Master Orchestrator - vision pipeline with LAZY page rendering.

Renders page 1 ONCE, classifies from it, decides target pages from the
doc_type, then renders ONLY the additional pages actually needed -
reusing the already-rendered page 1 bytes when page 1 is itself one of
the targets (e.g. SIGNED_OFFER_LETTER_JADE, where page 1 IS a target).
"""
import asyncio
from typing import Any, Dict, List, Optional

from app.pipeline.document_loader import DocumentLoader
from app.pipeline.stage1_vision_classification import classify_document
from app.pipeline.stage2_page_selection import select_target_pages
from app.pipeline.stage3_vision_extraction import process_document
from app.pipeline.stage4_rule_engine import evaluate_dossier
from backend.app.pipeline.stage5_decision_engine import generate_final_verdict


class OnboardingOrchestrator:
    def __init__(self, candidate_profile: Optional[Dict[str, Any]] = None):
        self.candidate_profile = candidate_profile or {"is_fresher": False}

    async def run_pipeline(self, uploaded_files: List[Dict[str, str]]) -> Dict[str, Any]:
        dossier: Dict[str, Any] = {}
        processing_errors: List[str] = []
        semaphore = asyncio.Semaphore(4)  # caps concurrent Azure vision calls

        async def _process_single_file(file_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
            filename, path = file_info.get("originalName"), file_info.get("storedPath")
            try:
                async with semaphore:
                    with DocumentLoader(path) as loader:
                        # Render page 1 exactly ONCE
                        page1_bytes = await asyncio.to_thread(loader.render_page, 0)

                        # Stage 1: classify from that single rendered page
                        classification = await classify_document(page1_bytes, filename)
                        doc_type = classification["document_type"]

                        if doc_type == "UNKNOWN":
                            return {
                                "document_type": "UNKNOWN", "confidence_score": classification["confidence_score"],
                                "extracted_data": {}, "originalName": filename, "storedPath": path,
                                "warning": "Could not classify this document from its first page.",
                            }

                        # Stage 2: decide which page NUMBERS are needed - nothing rendered yet
                        target_pages = select_target_pages(loader.page_count, doc_type)

                        # Render ONLY the additional pages actually needed, reusing
                        # page 1's bytes when it's already one of the targets - this
                        # is the fix for the double-render/double-classify issue
                        page_images: List[bytes] = []
                        for page_num in target_pages:
                            if page_num == 1:
                                page_images.append(page1_bytes)
                            else:
                                img_bytes = await asyncio.to_thread(loader.render_page, page_num - 1)
                                page_images.append(img_bytes)

                        # Stage 3: vision extraction from exactly the pages needed
                        extracted_doc = await process_document(page_images, doc_type, filename)
                        extracted_doc["confidence_score"] = classification["confidence_score"]
                        extracted_doc["storedPath"] = path
                        extracted_doc["originalName"] = filename
                        extracted_doc["pagesRead"] = target_pages
                        return extracted_doc

            except Exception as e:
                processing_errors.append(f"Failed processing {filename}: {str(e)}")
                return None

        completed_documents = await asyncio.gather(*[_process_single_file(f) for f in uploaded_files])

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

        rule_engine_result = evaluate_dossier(dossier)
        final_verdict = generate_final_verdict(rule_report=rule_engine_result, processing_errors=processing_errors)

        return {
            "status": final_verdict.get("status"),
            "action_items": final_verdict.get("action_items", []),
            "hr_context_notes": final_verdict.get("hr_context_notes", []),
            "summary": final_verdict.get("summary"),
            "pipeline_metrics": {"total_documents_processed": len(uploaded_files), "unclassified_documents": len(dossier.get("UNKNOWN", []))},
            "detailed_reports": {"step3_rule_engine": rule_engine_result, "processing_errors": processing_errors},
            "document_extractions": [doc for doc in completed_documents if doc],
        }