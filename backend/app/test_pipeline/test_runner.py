"""
test_pipeline/test_stage7_decision_engine.py

Runs the REAL pipeline end-to-end on every file in your test documents
folder - Stage 1 (vision classify) -> Stage 2 (page selection) ->
Stage 3 (vision extraction) -> grouped into a dossier exactly like
OnboardingOrchestrator does -> Stage 4 (evaluate_dossier) -> Stage 7
(generate_final_verdict). No synthetic/hand-crafted inputs anywhere -
every result shown comes from actually processing your real test
documents through the real pipeline.

Output is ordered for human readability, not test-style PASS/FAIL:
  1. The final verdict, up front
  2. How we got there - per-document stage detail
  3. A compact summary at the end
"""
import asyncio
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.pipeline.document_loader import DocumentLoader                  # noqa: E402
from app.pipeline.stage1_vision_classification import classify_document  # noqa: E402
from app.pipeline.stage2_page_selection import select_target_pages       # noqa: E402
from app.pipeline.stage3_vision_extraction import process_document, DOC_TYPE_FIELDS  # noqa: E402
from app.pipeline.stage4_rule_engine import evaluate_dossier             # noqa: E402
from app.pipeline.stage5_decision_engine import generate_final_verdict   # noqa: E402

TEST_DIR = os.path.join(BACKEND_ROOT, "app", "new_docs")
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")

STATUS_LABELS = {
    "VERIFIED": "✅ VERIFIED",
    "PENDING_DOCUMENTS": "🕒 PENDING DOCUMENTS",
    "NEEDS_HUMAN_REVIEW": "⚠️  NEEDS HUMAN REVIEW",
    "SYSTEM_ERROR": "❌ SYSTEM ERROR",
}


async def process_one_file(filename: str) -> dict:
    path = os.path.join(TEST_DIR, filename)
    try:
        with DocumentLoader(path) as loader:
            page1_bytes = await asyncio.to_thread(loader.render_page, 0)
            total_pages = loader.page_count

            classification = await classify_document(page1_bytes, filename)
            doc_type = classification["document_type"]

            if doc_type == "UNKNOWN" or doc_type not in DOC_TYPE_FIELDS:
                return {
                    "originalName": filename,
                    "document_type": "UNKNOWN",
                    "confidence_score": classification["confidence_score"],
                    "extracted_data": {},
                    "pagesRead": [],
                    "warning": "Could not classify this document from its first page.",
                }

            target_pages = select_target_pages(total_pages, doc_type)
            page_images = []
            for page_num in target_pages:
                if page_num == 1:
                    page_images.append(page1_bytes)
                else:
                    img_bytes = await asyncio.to_thread(loader.render_page, page_num - 1)
                    page_images.append(img_bytes)

        extracted_doc = await process_document(page_images, doc_type, filename)
        extracted_doc["confidence_score"] = classification["confidence_score"]
        extracted_doc["originalName"] = filename
        extracted_doc["storedPath"] = path
        extracted_doc["pagesRead"] = target_pages
        return extracted_doc

    except Exception as e:
        return {"originalName": filename, "error": f"Failed processing {filename}: {str(e)}"}


async def run_pipeline_on_all_files():
    """Silently processes every file, builds the dossier, runs Stage 4 + 7."""
    files = sorted(f for f in os.listdir(TEST_DIR) if f.lower().endswith(SUPPORTED_EXTENSIONS))

    dossier = {}
    processing_errors = []
    per_file_results = []

    print(f"Processing {len(files)} document(s)...")
    for filename in files:
        result = await process_one_file(filename)
        per_file_results.append(result)
        await asyncio.sleep(1)  # gentle on the vision endpoint

        if "error" in result:
            processing_errors.append(result["error"])
            continue

        doc_type = result.get("document_type", "UNKNOWN")
        if doc_type != "UNKNOWN":
            if doc_type in dossier:
                if not isinstance(dossier[doc_type], list):
                    dossier[doc_type] = [dossier[doc_type]]
                dossier[doc_type].append(result)
            else:
                dossier[doc_type] = result
        else:
            dossier.setdefault("UNKNOWN", []).append(result)

    rule_report = evaluate_dossier(dossier)
    final_verdict = generate_final_verdict(rule_report=rule_report, processing_errors=processing_errors)

    return per_file_results, rule_report, final_verdict


def print_verdict(final_verdict: dict):
    status = final_verdict["status"]
    label = STATUS_LABELS.get(status, status)

    print()
    print("=" * 70)
    print("  FINAL VERDICT")
    print("=" * 70)
    print(f"  {label}")
    print(f"  {final_verdict['summary']}")
    print()

    action_items = final_verdict.get("action_items", [])
    if action_items:
        print("  Action items:")
        for item in action_items:
            print(f"    • {item}")
    else:
        print("  No action items - nothing further needed.")
    print("=" * 70)


def print_stage_by_stage(per_file_results: list, rule_report: dict):
    print()
    print("-" * 70)
    print("  HOW WE GOT HERE")
    print("-" * 70)

    for result in per_file_results:
        filename = result.get("originalName", "unknown file")
        print(f"\n  📄 {filename}")

        if "error" in result:
            print(f"     ❌ Processing failed: {result['error']}")
            continue

        doc_type = result.get("document_type", "UNKNOWN")
        confidence = result.get("confidence_score")
        pages_read = result.get("pagesRead", [])

        print(f"     Stage 1 - Classified as : {doc_type}  (confidence: {confidence})")

        if doc_type == "UNKNOWN":
            print(f"     ⚠️  {result.get('warning', 'Could not classify this document.')}")
            continue

        print(f"     Stage 2 - Pages read     : {pages_read}")

        extracted_data = result.get("extracted_data", {})
        print("     Stage 3 - Fields extracted:")
        if extracted_data:
            for field, value in extracted_data.items():
                print(f"                 {field}: {value}")
        else:
            print("                 (nothing extracted)")

        shape_warnings = result.get("shape_warnings")
        if shape_warnings:
            print(f"     ⚠️  Shape warnings: {shape_warnings}")

        extraction_error = result.get("error")
        if extraction_error:
            print(f"     ❌ Extraction error: {extraction_error}")

    print(f"\n  Stage 4 - Rule engine findings:")
    issues = rule_report.get("issues", [])
    pending = rule_report.get("pending_documents", [])

    if issues:
        for issue in issues:
            print(f"     • {issue}")
    else:
        print("     No issues found.")

    if pending:
        print(f"\n  Deferred/pending documents:")
        for doc in pending:
            print(f"     • {doc}")

    print("-" * 70)


def print_summary(per_file_results: list, rule_report: dict, final_verdict: dict):
    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    classified = [r for r in per_file_results if "error" not in r and r.get("document_type") != "UNKNOWN"]
    unclassified = [r for r in per_file_results if "error" not in r and r.get("document_type") == "UNKNOWN"]
    failed = [r for r in per_file_results if "error" in r]

    print(f"  Documents processed   : {len(per_file_results)}")
    print(f"  Successfully classified: {len(classified)}")
    if unclassified:
        print(f"  Could not classify    : {len(unclassified)}  ({', '.join(r['originalName'] for r in unclassified)})")
    if failed:
        print(f"  Failed to process     : {len(failed)}  ({', '.join(r['originalName'] for r in failed)})")

    print(f"  Rule engine issues    : {len(rule_report.get('issues', []))}")
    print(f"  Pending documents     : {len(rule_report.get('pending_documents', []))}")
    print(f"  Final status          : {STATUS_LABELS.get(final_verdict['status'], final_verdict['status'])}")
    print("=" * 70)


async def main():
    if not os.path.exists(TEST_DIR):
        print(f"❌ Error: '{TEST_DIR}' does not exist.")
        return

    per_file_results, rule_report, final_verdict = await run_pipeline_on_all_files()

    print_verdict(final_verdict)
    print_stage_by_stage(per_file_results, rule_report)
    print_summary(per_file_results, rule_report, final_verdict)


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())