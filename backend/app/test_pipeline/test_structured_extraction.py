"""
test_pipeline/test_extraction_dump.py

Runs REAL OCR (stage2) -> REAL LLM classification+extraction (stage3,
process_document) on every document in test_documents/, and prints the
full JSON result for each - document_type, confidence_score,
extracted_data, and any shape_warnings - so you can inspect exactly what
the LLM is returning before it reaches the rule engine.

Doesn't touch the rule engine, decision engine, or vision checks - this
is purely "what did classification + extraction produce."
"""
import asyncio
import glob
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, BACKEND_DIR)

from app.pipeline.stage2_ocr_extraction import extract_text        # noqa: E402
from app.pipeline.stage3_structured_extraction import process_document  # noqa: E402

DOCS_DIR = os.path.join(BACKEND_DIR, "app", "valid_test_documents")
SUPPORTED_EXTENSIONS = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf")


def find_test_files() -> list:
    """Same duplicate-safe glob pattern as your test_runner.py."""
    unique_paths = set()
    for ext in SUPPORTED_EXTENSIONS:
        unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext)))
        unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext.upper())))
    return sorted(unique_paths)


async def process_one(path: str):
    filename = os.path.basename(path)
    file_meta = {"originalName": filename, "storedPath": path}

    print("=" * 80)
    print(f"FILE: {filename}")
    print("=" * 80)

    # Step 1: real OCR
    ocr_result = extract_text(file_meta)
    raw_text = ocr_result.get("rawText", "")

    print(f"OCR confidence: {ocr_result.get('ocrConfidence')}")
    print(f"OCR raw text ({len(raw_text)} chars):")
    print("-" * 40)
    print(raw_text if raw_text.strip() else "(empty - nothing extracted)")
    print("-" * 40)

    if not raw_text.strip():
        print("[SKIP] No text extracted - would be classified UNKNOWN, skipping LLM call\n")
        return {"filename": filename, "document_type": "UNKNOWN", "extracted_data": {}}

    # Step 2: real LLM classification + structured extraction
    result = await process_document(ocr_text=raw_text, original_filename=filename)

    print(f"\ndocument_type    : {result.get('document_type')}")
    print(f"confidence_score : {result.get('confidence_score')}")

    if result.get("error"):
        print(f"error            : {result.get('error')}")

    if result.get("shape_warnings"):
        print("shape_warnings   :")
        for w in result["shape_warnings"]:
            print(f"  - {w}")

    print("\nextracted_data (full JSON):")
    print(json.dumps(result.get("extracted_data", {}), indent=2))
    print()

    return {"filename": filename, **result}


async def main():
    print(f"Scanning: {DOCS_DIR}\n")
    file_paths = find_test_files()

    if not file_paths:
        print(f"No documents found in {DOCS_DIR}")
        return

    print(f"Found {len(file_paths)} file(s):")
    for p in file_paths:
        print(f"  - {os.path.basename(p)}")
    print()

    all_results = []
# in test_extraction_dump.py's main() loop
    for path in file_paths:
        result = await process_one(path)
        all_results.append(result)
        await asyncio.sleep(2)  # give the TPM window room to recover between calls

    # Final summary table - one line per doc, easy to eyeball at a glance
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for r in all_results:
        warn_count = len(r.get("shape_warnings", []))
        error = r.get("error")
        status = f"ERROR: {error}" if error else (f"{warn_count} shape warning(s)" if warn_count else "ok")
        print(f"  {r['filename']:<35} -> {r.get('document_type', 'UNKNOWN'):<25} [{status}]")

    # Dump everything as one big JSON blob at the end, for copy-paste/diffing
    print("\n" + "=" * 80)
    print("FULL RAW OUTPUT (all documents, JSON)")
    print("=" * 80)
    print(json.dumps(all_results, indent=2, default=str))


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())