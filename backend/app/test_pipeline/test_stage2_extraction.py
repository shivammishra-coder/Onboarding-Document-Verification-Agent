"""
test_pipeline/test_stage2_page_extraction.py

Runs the REAL pipeline: Stage 1 classify_document() -> Stage 2
extract_document_text() - against every file in your test documents
folder, and prints the full extracted text (not just a preview) so you
can visually confirm real page content is coming back, which pages were
read, and specifically verify the SIGNED_OFFER_LETTER_JADE page-slicing
behavior (should show pagesRead = [1, 6, 7, 8, 11, 12], not all pages).
"""
import asyncio
import os
import sys

import httpx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.pipeline.stage1_document_classification import classify_document  # noqa: E402
from app.pipeline.stage2_smart_extraction import extract_document_text       # noqa: E402
from app.pipeline.ollama_client import get_auth_tuple                       # noqa: E402

TEST_DIR = os.path.join(BACKEND_ROOT, "app", "valid_test_documents")
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")


async def run_one(filename: str, client: httpx.AsyncClient):
    filepath = os.path.join(TEST_DIR, filename)
    file_info = {"originalName": filename, "storedPath": filepath}

    print("=" * 80)
    print(f"FILE: {filename}")
    print("=" * 80)

    # Real Stage 1 - we need its doc_type to drive Stage 2's page-slicing decision
    classification = await classify_document(file_info, client)
    doc_type = classification.get("document_type", "UNKNOWN")
    print(f"Stage 1 classification: {doc_type}  (confidence: {classification.get('confidence_score')})")

    # Real Stage 2
    result = await extract_document_text(file_info, doc_type)

    print(f"pagesRead: {result['pagesRead']}")
    if result["error"]:
        print(f"ERROR: {result['error']}")

    print("-" * 80)
    print("EXTRACTED TEXT:")
    print("-" * 80)
    text = result["rawText"]
    print(text if text.strip() else "(empty - nothing extracted)")
    print()

    return {
        "filename": filename,
        "doc_type": doc_type,
        "pagesRead": result["pagesRead"],
        "textLength": len(text),
        "error": result["error"],
    }


async def main():
    if not os.path.exists(TEST_DIR):
        print(f"❌ Error: The directory '{TEST_DIR}' does not exist.")
        return

    files_to_test = sorted(f for f in os.listdir(TEST_DIR) if f.lower().endswith(SUPPORTED_EXTENSIONS))
    if not files_to_test:
        print(f"⚠️ No test documents found in {TEST_DIR}.")
        return

    print(f"Found {len(files_to_test)} file(s) to process.\n")

    summaries = []
    async with httpx.AsyncClient(timeout=120.0, auth=get_auth_tuple(), verify=False) as client:
        for filename in files_to_test:
            summary = await run_one(filename, client)
            summaries.append(summary)
            await asyncio.sleep(1)  # gentle on the Ollama endpoint

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for s in summaries:
        marker = "❌" if s["error"] else ("⚠️ " if s["textLength"] == 0 else "✅")
        print(f"  {marker} {s['filename']:<35} doc_type={s['doc_type']:<25} pagesRead={s['pagesRead']}  textLength={s['textLength']}")

    empty_count = sum(1 for s in summaries if s["textLength"] == 0)
    if empty_count:
        print(f"\n⚠️ {empty_count} file(s) returned empty text - check those individually above.")


if __name__ == "__main__":
    asyncio.run(main())