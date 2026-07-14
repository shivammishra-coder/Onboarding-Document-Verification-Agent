"""
test_pipeline/test_stage3_from_stage2.py

Tests the REAL Stage 3 process_document() fed with REAL OCR text produced
by the REAL Stage 2 extract_document_text() - no hand-typed/synthetic
strings anywhere. Chains Stage 1 (classify) -> Stage 2 (page-aware
extraction) -> Stage 3 (structured extraction) across every file in your
test documents folder, so what you see here is exactly what the full
pipeline would produce.
"""
import asyncio
import glob
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import httpx  # noqa: E402

from app.pipeline.ollama_client import get_auth_tuple  # noqa: E402
from app.pipeline.stage1_document_classification import classify_document  # noqa: E402
from app.pipeline.stage2_smart_extraction import extract_document_text  # noqa: E402
from app.pipeline.stage3_structured_extraction import process_document  # noqa: E402

DOCS_DIR = os.path.join(BACKEND_ROOT, "app", "valid_test_documents")
SUPPORTED_EXTENSIONS = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf")


def find_test_files():
    unique_paths = set()
    for ext in SUPPORTED_EXTENSIONS:
        unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext)))
        unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext.upper())))
    return sorted(unique_paths)


async def run_one(path: str, client: httpx.AsyncClient) -> dict:
    filename = os.path.basename(path)
    file_info = {"originalName": filename, "storedPath": path}

    print("=" * 80)
    print(f"FILE: {filename}")
    print("=" * 80)

    # ---- Stage 1: classify from page 1 ----
    classification = await classify_document(file_info, client)
    doc_type = classification["document_type"]
    print(f"[Stage 1] document_type   : {doc_type}  (confidence: {classification['confidence_score']})")

    if doc_type == "UNKNOWN":
        print("[SKIP] Stage 1 could not classify this file - nothing to feed into Stage 2/3\n")
        return {"filename": filename, "doc_type": "UNKNOWN", "skipped": True}

    # ---- Stage 2: real page-aware extraction, driven by the real doc_type ----
    extraction = await extract_document_text(file_info, doc_type)
    print(f"[Stage 2] pagesRead        : {extraction['pagesRead']}")
    print(f"[Stage 2] error            : {extraction['error']}")

    raw_text = extraction.get("rawText", "")
    print(f"[Stage 2] rawText ({len(raw_text)} chars):")
    print("-" * 40)
    print(raw_text if raw_text.strip() else "(empty - nothing extracted)")
    print("-" * 40)

    if extraction.get("error") or not raw_text.strip():
        print("[SKIP] Stage 2 produced no usable text - Stage 3 would have nothing to work with\n")
        return {"filename": filename, "doc_type": doc_type, "skipped": True, "stage2_error": extraction.get("error")}

    # ---- Stage 3: structured extraction from Stage 2's REAL rawText ----
    result = await process_document(
        ocr_text=raw_text, doc_type=doc_type, client=client, original_filename=filename,
    )

    extracted = result.get("extracted_data", {}) or {}
    shape_warnings = result.get("shape_warnings", [])
    error = result.get("error")

    print(f"\n[Stage 3] document_type    : {result.get('document_type')}")
    if error:
        print(f"[Stage 3] ❌ error         : {error}")
    else:
        for field_name, value in extracted.items():
            if value is None or value == "" or value == []:
                print(f"[Stage 3] ❌ {field_name:<28}: MISSING (null)")
            else:
                print(f"[Stage 3] ✅ {field_name:<28}: {value}")

    if shape_warnings:
        print("[Stage 3] ⚠️  shape_warnings:")
        for w in shape_warnings:
            print(f"           - {w}")

    print()

    return {
        "filename": filename,
        "doc_type": doc_type,
        "confidence_score": classification["confidence_score"],
        "pages_read": extraction["pagesRead"],
        "extracted_data": extracted,
        "shape_warnings": shape_warnings,
        "error": error,
        "skipped": False,
    }


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

    timeout = httpx.Timeout(120.0, connect=15.0)
    results = []

    async with httpx.AsyncClient(timeout=timeout, auth=get_auth_tuple(), verify=False) as client:
        for path in file_paths:
            # Sequential, not gathered - Stage 1 AND Stage 3 each make a
            # real Ollama call per file, so this is 2 calls/file - keep
            # them spaced out to avoid hammering the endpoint's rate limits.
            result = await run_one(path, client)
            results.append(result)
            await asyncio.sleep(1)

    # Summary table
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for r in results:
        if r.get("skipped"):
            print(f"  {r['filename']:<35} -> {r['doc_type']:<25} [SKIPPED]")
            continue
        warn_count = len(r.get("shape_warnings", []))
        status = f"ERROR: {r['error']}" if r.get("error") else (f"{warn_count} shape warning(s)" if warn_count else "ok")
        null_fields = [k for k, v in r.get("extracted_data", {}).items() if v is None or v == "" or v == []]
        null_note = f", {len(null_fields)} field(s) null" if null_fields else ""
        print(f"  {r['filename']:<35} -> {r['doc_type']:<25} [{status}{null_note}]")

    processed = [r for r in results if not r.get("skipped")]
    print(f"\n{len(processed)}/{len(results)} files made it through Stage 1 -> Stage 2 -> Stage 3")

    # Full raw JSON dump at the end
    print("\n" + "=" * 80)
    print("FULL RAW OUTPUT (JSON)")
    print("=" * 80)
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())