"""
test_pipeline/test_stage3_vision_extraction.py

Chains the REAL pipeline: Stage 1 classify_document() -> Stage 2
select_target_pages() -> DocumentLoader (renders only the pages actually
selected, reusing page 1's bytes when it's already a target, same as
OnboardingOrchestrator) -> Stage 3 process_document() - for every file
in your test documents folder. Prints the full extracted_data dict,
any shape_warnings, and any error, per file.
"""
import asyncio
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.pipeline.document_loader import DocumentLoader                # noqa: E402
from app.pipeline.stage1_vision_classification import classify_document  # noqa: E402
from app.pipeline.stage2_page_selection import select_target_pages       # noqa: E402
from app.pipeline.stage3_vision_extraction import process_document, DOC_TYPE_FIELDS  # noqa: E402

TEST_DIR = os.path.join(BACKEND_ROOT, "app", "valid_test_documents")
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")

# Fields we KNOW should come back non-null on these specific dummy test
# documents (from whatever generator produced them) - fill in what you
# know is genuinely printed on each, to catch silent extraction misses.
EXPECTED_NON_NULL_FIELDS = {
    "correct_pan.jpg": ["name", "dob", "pan_number"],
    "correct_aadhaar.jpg": ["name", "dob", "aadhaar_number"],
    "correct_marksheet.jpg": ["qualification_level", "passing_year"],
    "correct_resume.jpg": ["candidate_name"],
    "correct_offer_letter.jpg": ["candidate_name", "grade", "location"],
    "correct_pf_form_11.jpg": ["candidate_name", "account_number", "ifsc_code"],
    "correct_cancelled_cheque.jpg": ["account_number", "ifsc_code"],
    "correct_self_declaration.jpg": ["candidate_name", "doj"],
}


async def run_one(filename: str) -> dict:
    path = os.path.join(TEST_DIR, filename)
    print("=" * 80)
    print(f"FILE: {filename}")
    print("=" * 80)

    try:
        with DocumentLoader(path) as loader:
            page1_bytes = await asyncio.to_thread(loader.render_page, 0)
            total_pages = loader.page_count

            classification = await classify_document(page1_bytes, filename)
            doc_type = classification["document_type"]
            print(f"  Stage 1 classified as: {doc_type} (confidence {classification['confidence_score']})")

            if doc_type == "UNKNOWN" or doc_type not in DOC_TYPE_FIELDS:
                print(f"  ⚠️ Skipping extraction - doc_type '{doc_type}' has no field schema.\n")
                return {"filename": filename, "doc_type": doc_type, "status": "SKIP"}

            target_pages = select_target_pages(total_pages, doc_type)
            print(f"  Stage 2 selected pages: {target_pages}")

            # Same page-reuse logic as OnboardingOrchestrator: don't
            # re-render page 1 if it's already one of the targets.
            page_images = []
            for page_num in target_pages:
                if page_num == 1:
                    page_images.append(page1_bytes)
                else:
                    img_bytes = await asyncio.to_thread(loader.render_page, page_num - 1)
                    page_images.append(img_bytes)

        extracted = await process_document(page_images, doc_type, filename)

    except Exception as e:
        print(f"  ❌ Pipeline failed: {e}\n")
        return {"filename": filename, "doc_type": "ERROR", "status": "FAIL"}

    extracted_data = extracted.get("extracted_data", {})
    shape_warnings = extracted.get("shape_warnings", [])
    error = extracted.get("error")

    print(f"  extracted_data: {json.dumps(extracted_data, indent=2, ensure_ascii=False)}")
    if shape_warnings:
        print(f"  ⚠️ shape_warnings: {shape_warnings}")
    if error:
        print(f"  ❌ error: {error}")

    checks_passed = True
    if error:
        checks_passed = False
        print("  [FAIL] no top-level error expected")
    else:
        print("  [PASS] no top-level error")

    expected_fields = EXPECTED_NON_NULL_FIELDS.get(filename, [])
    for field in expected_fields:
        value = extracted_data.get(field)
        ok = value is not None
        checks_passed = checks_passed and ok
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] expected non-null field '{field}': got {value!r}")

    print()
    return {"filename": filename, "doc_type": doc_type, "status": "PASS" if checks_passed else "FAIL"}


async def main():
    if not os.path.exists(TEST_DIR):
        print(f"❌ Error: '{TEST_DIR}' does not exist.")
        return

    files = sorted(f for f in os.listdir(TEST_DIR) if f.lower().endswith(SUPPORTED_EXTENSIONS))
    if not files:
        print(f"⚠️ No test documents found in {TEST_DIR}.")
        return

    print(f"Found {len(files)} file(s).\n")

    results = []
    for filename in files:
        result = await run_one(filename)
        results.append(result)
        await asyncio.sleep(1)

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for r in results:
        print(f"  [{r['status']}]  {r['filename']:<35} -> {r['doc_type']}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    total_checked = sum(1 for r in results if r["status"] in ("PASS", "FAIL"))
    if total_checked:
        print(f"\n{passed}/{total_checked} documents fully extracted correctly")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())