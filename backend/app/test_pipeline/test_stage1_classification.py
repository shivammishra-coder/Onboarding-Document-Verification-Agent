"""
test_pipeline/test_stage1_vision_classification.py

Renders REAL page-1 images (via DocumentLoader) from every file in your
test documents folder and sends them straight to the REAL vision
classifier (classify_document) - no mocks, no OCR text step at all,
since this pipeline classifies directly from pixels.
"""
import asyncio
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.pipeline.document_loader import DocumentLoader              # noqa: E402
from app.pipeline.stage1_vision_classification import (               # noqa: E402
    classify_document,
    VALID_DOC_TYPES,
)

TEST_DIR = os.path.join(BACKEND_ROOT, "app", "valid_test_documents")
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")

# Fill in with filename -> expected doc_type for PASS/FAIL markers.
# Leave empty {} to just dump raw results.
EXPECTED_TYPES = {
    "correct_pan.jpg": "PAN_CARD",
    "correct_aadhaar.jpg": "AADHAAR_CARD",
    "correct_marksheet.jpg": "MARKSHEET",
    "correct_resume.jpg": "RESUME",
    "correct_offer_letter.jpg": "SIGNED_OFFER_LETTER_JADE",
    "correct_pf_form_11.jpg": "PF_FORM_11",
    "correct_cancelled_cheque.jpg": "CANCELLED_CHEQUE",
    "correct_self_declaration.jpg": "SELF_DECLARATION_FORM",
}


async def run_one(filename: str) -> dict:
    path = os.path.join(TEST_DIR, filename)
    print("=" * 80)
    print(f"FILE: {filename}")
    print("=" * 80)

    try:
        with DocumentLoader(path) as loader:
            page1_bytes = await asyncio.to_thread(loader.render_page, 0)
            page_count = loader.page_count
    except Exception as e:
        print(f"  ❌ Failed to load/render page 1: {e}\n")
        return {"filename": filename, "document_type": "ERROR", "confidence_score": 0.0, "status": "FAIL"}

    print(f"  page_count reported by DocumentLoader: {page_count}")

    result = await classify_document(page1_bytes, filename)
    doc_type = result["document_type"]
    confidence = result["confidence_score"]

    expected = EXPECTED_TYPES.get(filename)
    status = None
    if expected is not None:
        status = "PASS" if doc_type == expected else "FAIL"

    # Sanity checks independent of any expected-value mapping
    sanity_checks = [
        ("document_type is a valid known type", doc_type in VALID_DOC_TYPES),
        ("confidence_score is a float in [0, 1]", isinstance(confidence, (int, float)) and 0 <= confidence <= 1),
    ]

    print(f"  document_type    : {doc_type}" + (f"   [{status}] (expected: {expected})" if status else ""))
    print(f"  confidence_score : {confidence}")
    for desc, ok in sanity_checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {desc}")
    print()

    return {"filename": filename, "document_type": doc_type, "confidence_score": confidence, "status": status}


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
        await asyncio.sleep(1)  # gentle on the vision endpoint

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for r in results:
        marker = f"[{r['status']}]" if r["status"] else ""
        print(f"  {r['filename']:<35} -> {r['document_type']:<25} (conf: {r['confidence_score']:<4}) {marker}")

    checked = [r for r in results if r["status"] is not None]
    if checked:
        passed = sum(1 for r in checked if r["status"] == "PASS")
        print(f"\n{passed}/{len(checked)} documents classified as expected")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())