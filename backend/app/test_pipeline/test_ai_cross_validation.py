"""
test_pipeline/test_ai_cross_validation.py

Chains the REAL stage2 (OCR) -> stage1 (classification) -> stage3
(structured extraction) -> stage4 (rule engine) end to end, no mocks, to
get real `structured` AND real `rule_result` dicts - then feeds those
real dicts into stage5's `ai_cross_validate`. Nothing here is a
hand-crafted structured/rule_result dict; where a specific scenario
(e.g. a rule mismatch, a missing name) can't occur on the clean sample
document as-is, we get it by rerunning the REAL run_document_rules()
with a different candidate profile, or by mutating exactly one field on
a real structured dict (same pattern as test_rule_engine.py) - never by
typing a fake dict from scratch.

Covers:
  - A clean/matching document (rule engine passes) -> low semantic risk
  - The SAME structured dict rerun through run_document_rules with a
    mismatched profile (rule engine fails, for real) -> higher risk
  - A structured dict with 'name' mutated to None -> higher risk
  - The heuristic formula itself, using the same real dicts above
  - The real Groq LLM path (if GROQ_API_KEY is set)
  - Forced Groq failure -> confirms fallback to heuristic (also only
    meaningful if GROQ_API_KEY is set)
"""
import asyncio
import copy
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, BACKEND_DIR)

from app.config import GROQ_API_KEY                                          # noqa: E402
from app.pipeline.stage2_ocr_extraction import extract_text                  # noqa: E402
from app.pipeline.stage1_document_classification import classify_document    # noqa: E402
from app.pipeline.stage3_structured_extraction import structured_extraction  # noqa: E402
from app.pipeline.stage4_rule_engine import run_document_rules               # noqa: E402
import app.pipeline.stage5_ai_cross_validation as stage5                     # noqa: E402
from app.pipeline.stage5_ai_cross_validation import (                        # noqa: E402
    ai_cross_validate,
    _heuristic_cross_validate,
)

TEST_DOCS_DIR = os.path.join(BACKEND_DIR, "app", "test_documents")

CANDIDATE_TRUE_NAME = "Rahul Kumar Sharma"
CANDIDATE_TRUE_DOB = "1998-04-15"
MISMATCHED_NAME = "Amit Verma"

ID_DOC_FILES = ["pan_card.jpg", "aadhaar_card.jpg"]


async def get_real_structured(filename: str):
    path = os.path.join(TEST_DOCS_DIR, filename)
    if not os.path.exists(path):
        return None, None
    file_meta = {"originalName": filename, "storedPath": path}
    ocr_result = extract_text(file_meta)
    classification = classify_document(file_meta, ocr_text=ocr_result["rawText"])
    structured = await structured_extraction(classification["docType"], ocr_result["rawText"])
    return classification, structured


async def run_clean_document_scenario(filename: str):
    """Matching profile -> real rule engine passes -> expect LOW risk."""
    classification, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    print(f"  {filename} (classified as {classification['docType']}) - clean/matching scenario")
    rule_result = run_document_rules(structured, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})
    ai_result = await ai_cross_validate(structured, rule_result)
    print(f"    rule_result: {rule_result}")
    print(f"    ai_result  : {ai_result}")

    checks = [
        ("rule engine actually passed (precondition)", rule_result["passed"] is True),
        ("semanticRisk is a number in [0, 1]", isinstance(ai_result["semanticRisk"], (int, float)) and 0 <= ai_result["semanticRisk"] <= 1),
        ("notes is a list", isinstance(ai_result["notes"], list)),
        ("source is groq/heuristic/heuristic_fallback", ai_result["source"] in ("groq", "heuristic", "heuristic_fallback")),
        ("semanticRisk is on the LOW side for a clean, rule-passing doc (< 0.5)", ai_result["semanticRisk"] < 0.5),
    ]

    all_passed = True
    for desc, ok in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"    [{marker}] {desc}")
        all_passed = all_passed and ok
    print()
    return all_passed


async def run_mismatched_profile_scenario(filename: str):
    """
    SAME real structured dict as the clean scenario, rerun through the
    REAL run_document_rules with a mismatched profile - producing a
    genuine rule_result with real issues, not a hand-crafted one.
    """
    classification, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    print(f"  {filename} (classified as {classification['docType']}) - name-mismatch scenario")
    clean_rule_result = run_document_rules(structured, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})
    mismatched_rule_result = run_document_rules(structured, {"name": MISMATCHED_NAME, "dob": CANDIDATE_TRUE_DOB})

    clean_ai_result = await ai_cross_validate(structured, clean_rule_result)
    mismatched_ai_result = await ai_cross_validate(structured, mismatched_rule_result)
    print(f"    mismatched rule_result: {mismatched_rule_result}")
    print(f"    mismatched ai_result  : {mismatched_ai_result}")

    checks = [
        ("mismatched rule_result actually has issues (precondition)", len(mismatched_rule_result["issues"]) > 0),
        ("mismatched semanticRisk >= clean semanticRisk", mismatched_ai_result["semanticRisk"] >= clean_ai_result["semanticRisk"]),
        ("mismatched notes list is non-empty", len(mismatched_ai_result["notes"]) > 0),
    ]

    all_passed = True
    for desc, ok in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"    [{marker}] {desc}  (clean risk={clean_ai_result['semanticRisk']}, mismatched risk={mismatched_ai_result['semanticRisk']})")
        all_passed = all_passed and ok
    print()
    return all_passed


async def run_missing_name_scenario(filename: str):
    """
    Real structured dict with 'name' mutated to None (same mutation
    pattern as test_rule_engine.py) -> real rule engine raises the
    generic name-detection issue -> expect elevated risk.
    """
    classification, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    print(f"  {filename} (classified as {classification['docType']}) - missing-name scenario")
    mutated = copy.deepcopy(structured)
    mutated["name"] = None

    rule_result = run_document_rules(mutated, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})
    ai_result = await ai_cross_validate(mutated, rule_result)
    print(f"    rule_result: {rule_result}")
    print(f"    ai_result  : {ai_result}")

    checks = [
        ("rule_result flags the missing name (precondition)", any("name" in issue.lower() for issue in rule_result["issues"])),
        ("semanticRisk reflects elevated risk (> 0)", ai_result["semanticRisk"] > 0),
    ]

    all_passed = True
    for desc, ok in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"    [{marker}] {desc}")
        all_passed = all_passed and ok
    print()
    return all_passed


async def run_heuristic_formula_unit_tests(filename: str):
    """
    Deterministic checks of _heuristic_cross_validate's exact formula
    (0.3 for rule issues present, +0.2 for a missing/unreadable name,
    capped at 1.0) - using REAL structured dicts (stage3) and REAL
    rule_result dicts (stage4, via different profiles), same as every
    other scenario above.

    NOTE: there is no reachable real-data case for "issues absent AND
    name missing" - the rule engine's generic check ALWAYS raises an
    issue the moment name is missing, regardless of what profile is
    supplied, so those two conditions can never occur independently in
    a genuine rule_result. That 4th combination is intentionally
    omitted rather than faked.
    """
    print("-" * 70)
    print("UNIT TESTS: _heuristic_cross_validate scoring formula (real dicts)")
    print("-" * 70)

    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    missing_name_structured = copy.deepcopy(structured)
    missing_name_structured["name"] = None

    cases = [
        {
            "name": "no_issues_name_present",
            "structured": structured,
            "rule_result": run_document_rules(structured, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB}),
            "expect_risk": 0.0,
        },
        {
            "name": "issues_present_name_present",
            "structured": structured,
            "rule_result": run_document_rules(structured, {"name": MISMATCHED_NAME, "dob": CANDIDATE_TRUE_DOB}),
            "expect_risk": 0.3,
        },
        {
            "name": "issues_present_name_missing",
            "structured": missing_name_structured,
            "rule_result": run_document_rules(missing_name_structured, {"name": MISMATCHED_NAME, "dob": CANDIDATE_TRUE_DOB}),
            "expect_risk": 0.5,
        },
    ]

    all_passed = True
    for case in cases:
        result = _heuristic_cross_validate(case["structured"], case["rule_result"])
        ok = result["semanticRisk"] == case["expect_risk"] and result["source"] == "heuristic"
        all_passed = all_passed and ok
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {case['name']}: rule_issues={case['rule_result']['issues']}")
        print(f"      expected_risk={case['expect_risk']}, got={result['semanticRisk']}, notes={result['notes']}")

    print(f"  {'ALL PASS' if all_passed else 'SOME FAILED'}\n")
    return all_passed


async def run_real_groq_path_test(filename: str):
    """Confirms the real Groq call path is actually used when GROQ_API_KEY is set."""
    print("-" * 70)
    print("TEST: Real Groq LLM path (only runs if GROQ_API_KEY is set)")
    print("-" * 70)

    if not GROQ_API_KEY:
        print("  [SKIP] GROQ_API_KEY not set\n")
        return None

    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    rule_result = run_document_rules(structured, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})
    ai_result = await ai_cross_validate(structured, rule_result)

    ok = (
        ai_result["source"] == "groq"
        and isinstance(ai_result["semanticRisk"], (int, float))
        and 0 <= ai_result["semanticRisk"] <= 1
        and isinstance(ai_result["notes"], list)
    )
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] result: {ai_result}\n")
    return ok


async def run_groq_failure_fallback_test(filename: str):
    """
    Forces the real Groq call to fail (temporarily pointing at an
    invalid URL) and confirms ai_cross_validate falls back to the
    heuristic rather than raising - using a real structured/rule_result
    pair. Only meaningful if GROQ_API_KEY is set.
    """
    print("-" * 70)
    print("TEST: Groq call failure -> graceful fallback to heuristic")
    print("-" * 70)

    if not GROQ_API_KEY:
        print("  [SKIP] GROQ_API_KEY not set - ai_cross_validate already uses the heuristic path directly\n")
        return None

    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    rule_result = run_document_rules(structured, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})

    original_url = stage5.GROQ_API_URL
    stage5.GROQ_API_URL = "https://api.groq.com/openai/v1/this-endpoint-does-not-exist"
    try:
        ai_result = await ai_cross_validate(structured, rule_result)
    finally:
        stage5.GROQ_API_URL = original_url

    ok = ai_result["source"] == "heuristic_fallback" and "error" in ai_result
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] source={ai_result['source']!r}, error present={'error' in ai_result}")
    print(f"      full result: {ai_result}\n")
    return ok


async def main():
    print(f"TEST_DOCS_DIR = {TEST_DOCS_DIR}")
    print(f"GROQ_API_KEY set: {bool(GROQ_API_KEY)}\n")
    print("=" * 70)
    print("OCR -> CLASSIFICATION -> STRUCTURED EXTRACTION -> RULE ENGINE -> AI CROSS-VALIDATION")
    print("=" * 70)

    results = []

    for filename in ID_DOC_FILES:
        r = await run_clean_document_scenario(filename)
        if r is not None:
            results.append((f"clean:{filename}", r))

    for filename in ID_DOC_FILES:
        r = await run_mismatched_profile_scenario(filename)
        if r is not None:
            results.append((f"mismatched:{filename}", r))

    for filename in ID_DOC_FILES:
        r = await run_missing_name_scenario(filename)
        if r is not None:
            results.append((f"missing_name:{filename}", r))

    r = await run_heuristic_formula_unit_tests(ID_DOC_FILES[0])
    if r is not None:
        results.append(("heuristic_formula_unit_tests", r))

    r = await run_real_groq_path_test(ID_DOC_FILES[0])
    if r is not None:
        results.append(("real_groq_path", r))

    r = await run_groq_failure_fallback_test(ID_DOC_FILES[0])
    if r is not None:
        results.append(("groq_failure_fallback", r))

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    failed = sum(1 for _, passed in results if not passed)
    print(f"\n{len(results) - failed}/{len(results)} test groups fully passed")


if __name__ == "__main__":
    asyncio.run(main())