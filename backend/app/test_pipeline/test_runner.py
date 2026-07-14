import os
import sys
import glob
import asyncio
import json
from typing import List, Dict

# --- PATH FIX ---
backend_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.pipeline.orchestrator import OnboardingOrchestrator

# Point this to the folder containing your test documents
DOCS_DIR = os.path.join(backend_root, "app", "valid_test_documents")


def print_audit_trail(result: Dict):
    """Formats the final pipeline output into a clean, readable dashboard."""
    print(f"\n{'='*80}")
    print("🚀 END-TO-END PIPELINE EXECUTION COMPLETE")
    print(f"{'='*80}")

    # 1. High-Level Summary
    status = result.get("status", "UNKNOWN")
    status_icon = "🟢" if status == "VERIFIED" else "🟡" if status == "PENDING_DOCUMENTS" else "🔴"

    print("\n▶ FINAL DECISION ENGINE STATUS")
    print(f"  - STATUS  : {status_icon} {status}")
    print(f"  - SUMMARY : {result.get('summary')}")
    print(f"  - DOCS    : Processed {result['pipeline_metrics'].get('total_documents_processed')} files.")
    print(f"  - UNKNOWN : {result['pipeline_metrics'].get('unclassified_documents')} document(s) could not be classified.")

    # 2. Per-document classification + page-extraction + field breakdown
    print("\n▶ PER-DOCUMENT CLASSIFICATION & EXTRACTION")
    for doc in result.get("document_extractions", []):
        filename = doc.get("originalName", "?")
        doc_type = doc.get("document_type", "UNKNOWN")
        confidence = doc.get("confidence_score", 0.0)
        pages_read = doc.get("pagesRead", [])
        extracted = doc.get("extracted_data", {}) or {}
        shape_warnings = doc.get("shape_warnings", [])
        error = doc.get("error")
        warning = doc.get("warning")

        print(f"\n  📄 {filename}")
        print(f"     document_type    : {doc_type}  (confidence: {confidence})")
        if pages_read:
            # Confirms Stage 2's page-slicing actually did what you told it to -
            # e.g. SIGNED_OFFER_LETTER_JADE should show [1, 6, 7, 8, 11, 12]
            # (or fewer, if the PDF has fewer pages), everything else shows
            # the full page range it read.
            print(f"     pages_read       : {pages_read}")

        if error:
            print(f"     ❌ error         : {error}")
            continue

        if warning:
            print(f"     ⚠️  warning       : {warning}")

        if not extracted:
            print("     (no fields expected/extracted for this type)")
        else:
            for field_name, value in extracted.items():
                if value is None or value == "" or value == []:
                    print(f"     ❌ {field_name:<28}: MISSING (null)")
                else:
                    print(f"     ✅ {field_name:<28}: {value}")

        if shape_warnings:
            print("     ⚠️  shape_warnings:")
            for w in shape_warnings:
                print(f"        - {w}")

    # 3. Action Items (Failures)
    action_items = result.get("action_items", [])
    if action_items:
        print("\n▶ REQUIRED ACTION ITEMS (FAILURES):")
        for item in action_items:
            print(f"    🚩 {item}")

    # 4. AI Context Notes
    notes = result.get("hr_context_notes", [])
    if notes:
        print("\n▶ AI AUDITOR NOTES (CONTEXT):")
        for note in notes:
            print(f"    💡 {note}")

    # 5. Processing errors (OCR/page-extraction failures that skipped a doc entirely)
    processing_errors = result.get("detailed_reports", {}).get("processing_errors", [])
    if processing_errors:
        print("\n▶ PROCESSING ERRORS (documents excluded from the dossier entirely):")
        for err in processing_errors:
            print(f"    ⛔ {err}")

    # 6. Raw JSON block for full debugging
    print(f"\n{'='*80}")
    print("RAW PIPELINE OUTPUT (JSON):")
    print(json.dumps(result, indent=2))
    print(f"{'='*80}\n")


async def main():
    print(f"\nScanning for documents in: {DOCS_DIR}")

    supported_extensions = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf")

    unique_file_paths = set()
    for ext in supported_extensions:
        unique_file_paths.update(glob.glob(os.path.join(DOCS_DIR, ext)))
        unique_file_paths.update(glob.glob(os.path.join(DOCS_DIR, ext.upper())))

    file_paths = list(unique_file_paths)

    if not file_paths:
        print(f"⚠️ No documents found in {DOCS_DIR}. Please add some test files and try again.")
        return

    uploaded_files: List[Dict[str, str]] = []
    for path in file_paths:
        uploaded_files.append({
            "originalName": os.path.basename(path),
            "storedPath": path
        })
        print(f"  📎 Loaded: {os.path.basename(path)}")

    print("\n⚙️  Firing up the pipeline (Stage 1 classify -> Stage 2 page extraction ->")
    print("    Stage 3 structured extraction -> Stage 4 rule engine -> Stage 5 decision)...")
    print("    Note: Stage 1 and Stage 3 each make one Ollama call per document,")
    print("    so total wait time scales with document count and endpoint latency.\n")

    orchestrator = OnboardingOrchestrator()
    final_result = await orchestrator.run_pipeline(uploaded_files)

    print_audit_trail(final_result)


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())