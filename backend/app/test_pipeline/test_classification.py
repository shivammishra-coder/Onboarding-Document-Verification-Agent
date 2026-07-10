"""
test_pipeline/test_classification.py

Chains the REAL stage2 (OCR) output into the REAL stage1 (classification)
function - end to end, no mocks - so you see how classification holds up
against actual OCR noise, not clean hand-written text.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, BACKEND_DIR)

from app.pipeline.stage2_ocr_extraction import extract_text        # noqa: E402
from app.pipeline.stage1_document_classification import classify_document  # noqa: E402

TEST_DOCS_DIR = os.path.join(BACKEND_DIR, "app", "test_documents")

# (filename, expected_doc_type) - lets us print PASS/FAIL, not just output
DOCS_TO_TEST = [
    ("aadhaar_card.jpg", "AADHAAR_CARD"),
    ("aadhaar_card.pdf", "AADHAAR_CARD"),
    ("pan_card.jpg", "PAN_CARD"),
    ("pan_card.pdf", "PAN_CARD"),
    ("marksheet_10th.jpg", "MARKSHEET"),
    ("marksheet_10th.pdf", "MARKSHEET"),
    ("payslip.jpg", "PAYSLIP"),
    ("payslip.pdf", "PAYSLIP"),
    ("cancelled_cheque.jpg", "CANCELLED_CHEQUE"),
    ("cancelled_cheque.pdf", "CANCELLED_CHEQUE"),
]


def run_one(filename: str, expected_type: str):
    path = os.path.join(TEST_DOCS_DIR, filename)
    if not os.path.exists(path):
        print(f"  [SKIP] {filename} not found\n")
        return

    file_meta = {"originalName": filename, "storedPath": path}

    ocr_result = extract_text(file_meta)
    classification = classify_document(file_meta, ocr_text=ocr_result["rawText"])

    passed = classification["docType"] == expected_type
    status = "PASS" if passed else "FAIL"

    print(f"  {filename}")
    print(f"    expected: {expected_type}")
    print(f"    got:      {classification['docType']}  (confidence: {classification['confidence']})")
    print(f"    OCR confidence: {ocr_result['ocrConfidence']}")
    print(f"    [{status}]\n")


if __name__ == "__main__":
    print(f"TEST_DOCS_DIR = {TEST_DOCS_DIR}\n")
    print("=" * 70)
    print("OCR -> CLASSIFICATION (end-to-end, real pipeline functions)")
    print("=" * 70)
    for filename, expected_type in DOCS_TO_TEST:
        run_one(filename, expected_type)