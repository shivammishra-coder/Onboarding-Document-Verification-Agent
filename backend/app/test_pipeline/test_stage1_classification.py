# """
# test_pipeline/test_stage1_classification.py

# Runs the REAL Stage 1 classify_document() against every file in your test
# documents folder - no mocks, real EasyOCR + real Ollama call - and prints
# what it classified each one as, its confidence, and the first-page text
# sample it worked from, so you can see exactly what Stage 1 is doing in
# isolation before Stage 2/3 ever run.
# """
# import asyncio
# import glob
# import json
# import os
# import sys

# # --- PATH FIX (same pattern as your other test scripts) ---
# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
# if BACKEND_ROOT not in sys.path:
#     sys.path.insert(0, BACKEND_ROOT)

# import httpx  # noqa: E402

# from app.pipeline.ollama_client import get_auth_tuple  # noqa: E402
# from app.pipeline.stage1_document_classification import classify_document  # noqa: E402

# DOCS_DIR = os.path.join(BACKEND_ROOT, "app", "valid_test_documents")
# SUPPORTED_EXTENSIONS = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf")

# # Optional: fill this in with filename -> expected doc_type to get PASS/FAIL
# # markers instead of just raw output. Leave empty {} to just dump results.
# EXPECTED_TYPES = {
#     "correct_pan.jpg": "PAN_CARD",
#     "correct_aadhaar.jpg": "AADHAAR_CARD",
#     "correct_marksheet.jpg": "MARKSHEET",
#     "correct_resume.jpg": "RESUME",
#     "correct_offer_letter.jpg": "SIGNED_OFFER_LETTER_JADE",
#     "correct_pf_form_11.jpg": "PF_FORM_11",
#     "correct_cancelled_cheque.jpg": "CANCELLED_CHEQUE",
#     "correct_self_declaration.jpg": "SELF_DECLARATION_FORM",
#     "signed_offer_letter_jade.jpg": "SIGNED_OFFER_LETTER_JADE",
# }


# def find_test_files():
#     unique_paths = set()
#     for ext in SUPPORTED_EXTENSIONS:
#         unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext)))
#         unique_paths.update(glob.glob(os.path.join(DOCS_DIR, ext.upper())))
#     return sorted(unique_paths)


# async def run_one(path: str, client: httpx.AsyncClient) -> dict:
#     filename = os.path.basename(path)
#     file_info = {"originalName": filename, "storedPath": path}

#     result = await classify_document(file_info, client)

#     expected = EXPECTED_TYPES.get(filename)
#     got = result["document_type"]
#     status = None
#     if expected is not None:
#         status = "PASS" if got == expected else "FAIL"

#     print("=" * 80)
#     print(f"FILE: {filename}")
#     print("=" * 80)
#     print(f"document_type    : {got}" + (f"   [{status}] (expected: {expected})" if status else ""))
#     print(f"confidence_score : {result['confidence_score']}")
#     print("firstPageTextPreview:")
#     print("-" * 40)
#     preview = result.get("firstPageTextPreview", "")
#     print(preview if preview.strip() else "(empty - nothing extracted from page 1)")
#     print("-" * 40)
#     print()

#     return {"filename": filename, **result, "status": status}


# async def main():
#     print(f"Scanning: {DOCS_DIR}\n")
#     file_paths = find_test_files()

#     if not file_paths:
#         print(f"No documents found in {DOCS_DIR}")
#         return

#     print(f"Found {len(file_paths)} file(s):")
#     for p in file_paths:
#         print(f"  - {os.path.basename(p)}")
#     print()

#     timeout = httpx.Timeout(120.0, connect=15.0)
#     results = []

#     async with httpx.AsyncClient(timeout=timeout, auth=get_auth_tuple(), verify=False) as client:
#         for path in file_paths:
#             # Sequential, not gathered concurrently - keeps output readable
#             # and avoids hammering the Ollama endpoint's rate limits all at once.
#             result = await run_one(path, client)
#             results.append(result)
#             await asyncio.sleep(1)  # small gap between calls

#     # Summary table
#     print("=" * 80)
#     print("SUMMARY")
#     print("=" * 80)
#     for r in results:
#         marker = f"[{r['status']}]" if r["status"] else ""
#         print(f"  {r['filename']:<35} -> {r['document_type']:<25} (conf: {r['confidence_score']:<4}) {marker}")

#     if EXPECTED_TYPES:
#         checked = [r for r in results if r["status"] is not None]
#         passed = sum(1 for r in checked if r["status"] == "PASS")
#         print(f"\n{passed}/{len(checked)} documents classified as expected")

#     # Full raw JSON dump at the end, for copy/paste or diffing
#     print("\n" + "=" * 80)
#     print("FULL RAW OUTPUT (JSON)")
#     print("=" * 80)
#     print(json.dumps(results, indent=2))


# if __name__ == "__main__":
#     if os.name == "nt":
#         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     asyncio.run(main())


import asyncio
import os
import sys
import httpx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.pipeline.stage1_document_classification import classify_document
from app.pipeline.ollama_client import get_auth_tuple   # ← add this

TEST_DIR = os.path.join(BACKEND_ROOT, "app", "valid_test_documents")

async def run_classification_tests():
    if not os.path.exists(TEST_DIR):
        print(f"❌ Error: The directory '{TEST_DIR}' does not exist.")
        return

    files_to_test = [f for f in os.listdir(TEST_DIR) if f.endswith(('.png', '.jpg', '.jpeg', '.pdf'))]
    if not files_to_test:
        print(f"⚠️ No test images found in {TEST_DIR}.")
        return

    print(f"🚀 Starting classification test on {len(files_to_test)} documents...\n")
    print("=" * 60)

    # ← the fix: attach Basic Auth + skip TLS verification for the internal endpoint
    async with httpx.AsyncClient(timeout=120.0, auth=get_auth_tuple(), verify=False) as client:
        for filename in files_to_test:
            filepath = os.path.join(TEST_DIR, filename)
            file_info = {"originalName": filename, "storedPath": filepath}

            print(f"📄 Processing: {filename}...")
            try:
                result = await classify_document(file_info, client)
                doc_type = result.get('document_type')
                confidence = result.get('confidence_score')
                status_icon = "✅" if doc_type != "UNKNOWN" else "⚠️"
                print(f"   {status_icon} Detected Type: {doc_type}")
                print(f"   📊 Confidence:    {confidence}")
                preview = result.get('firstPageTextPreview', '').replace('\n', ' ')
                print(f"   👁️  OCR Preview:  {preview[:60]}...")
            except Exception as e:
                print(f"   ❌ Failed to process {filename}: {e}")
            print("-" * 60)

    print("🏁 Classification Testing Complete!")

if __name__ == "__main__":
    asyncio.run(run_classification_tests())