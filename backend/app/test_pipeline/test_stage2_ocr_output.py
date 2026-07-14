"""
test_pipeline/test_stage2_ocr_output.py

Minimal test - just runs the REAL Stage 2 extract_document_text() against
every real file in your test documents folder and prints the extracted
rawText. No synthetic data, no assertions, no pass/fail - just the OCR
output itself.
"""
import asyncio
import glob
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.pipeline.stage2_smart_extraction import extract_document_text  # noqa: E402

DOCS_DIR = os.path.join(BACKEND_ROOT, "app", "valid_test_documents")
SUPPORTED_EXTENSIONS = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf")


def find_test_files():
    unique_paths = set()
    for ext in SUPPORTED_EXTENSIONS:
        unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext)))
        unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext.upper())))
    return sorted(unique_paths)


async def main():
    print(f"Scanning: {DOCS_DIR}\n")
    file_paths = find_test_files()

    if not file_paths:
        print(f"No documents found in {DOCS_DIR}")
        return

    for path in file_paths:
        filename = os.path.basename(path)
        file_info = {"originalName": filename, "storedPath": path}

        # doc_type only matters for SIGNED_OFFER_LETTER_JADE's special page
        # slicing - use that when the filename hints at it, otherwise a
        # generic type reads ALL pages, which is what you want for a plain
        # "show me the OCR text" check.
        doc_type = "SIGNED_OFFER_LETTER_JADE" if "jade" in filename.lower() or "signed_offer" in filename.lower() else "GENERIC"

        result = await extract_document_text(file_info, doc_type)

        print("=" * 80)
        print(f"FILE: {filename}")
        print("=" * 80)
        print(f"pagesRead: {result['pagesRead']}")
        print(f"error: {result['error']}")
        print("-" * 80)
        print(result["rawText"] if result["rawText"].strip() else "(empty - nothing extracted)")
        print("-" * 80)
        print()


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())