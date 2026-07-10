"""
test_pipeline/test_rule_engine.py

Chains the REAL stage2 (OCR) -> stage1 (classification) -> stage3
(structured extraction) end to end, no mocks, to get real `structured`
dicts - then runs stage4's `run_document_rules` against those real dicts
under several candidate-profile scenarios.

Every scenario shares ONE consistent candidate identity (CANDIDATE_TRUE_NAME
/ CANDIDATE_TRUE_DOB, matching what's actually printed on the dummy test
documents per generate_test_documents.py) - all "wrong" variants are
derived from that single source of truth rather than separately typed
literals, so there's no risk of the test data itself being inconsistent.

A few rule-engine branches (invalid Aadhaar length, a missing DOB field,
etc.) can't be triggered by the clean sample documents as-is. For those,
we take a COPY of the real structured dict returned by structured_extraction()
and mutate exactly one field to simulate an extraction miss - clearly
labeled inline - rather than fabricating a synthetic dict from scratch.

Also unit-tests check_mandatory_documents and the internal name-matching
helper directly, since those don't operate on a "structured doc" at all.
"""
import asyncio
import copy
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, BACKEND_DIR)

from app.pipeline.stage2_ocr_extraction import extract_text                      # noqa: E402
from app.pipeline.stage1_document_classification import classify_document        # noqa: E402
from app.pipeline.stage3_structured_extraction import structured_extraction      # noqa: E402
from app.pipeline.stage4_rule_engine import (                                    # noqa: E402
    run_document_rules,
    check_mandatory_documents,
    _names_roughly_match,
    MANDATORY_DOC_TYPES,
)

TEST_DOCS_DIR = os.path.join(BACKEND_DIR, "app", "test_documents")

# ---------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH for candidate identity - matches what's actually
# printed on every dummy test document (see generate_test_documents.py).
# Every scenario below derives from these two constants instead of
# re-typing name/DOB literals, so the test data can't drift out of sync
# with itself.
# ---------------------------------------------------------------------
CANDIDATE_TRUE_NAME = "Rahul Kumar Sharma"
CANDIDATE_TRUE_DOB = "15/04/1998"

# A name that shares no words with CANDIDATE_TRUE_NAME (genuine mismatch)
MISMATCHED_NAME = "Amit Verma"
# A DOB that's simply wrong (genuine mismatch)
MISMATCHED_DOB = "2000-01-01"
# Same name, reordered + different case - derived FROM the true name, not
# a separately typed literal, to prove _names_roughly_match is truly
# order/case-insensitive rather than happening to match one fixed string.
REORDERED_CASE_NAME = " ".join(reversed(CANDIDATE_TRUE_NAME.upper().split()))

ID_DOC_FILES = ["aadhaar_card.jpg", "aadhaar_card.pdf", "pan_card.jpg", "pan_card.pdf"]
NON_ID_DOC_FILES = ["marksheet_10th.jpg", "payslip.jpg", "cancelled_cheque.jpg"]

# Candidate-profile scenarios run against every real PAN/Aadhaar structured
# dict. All built from the two constants above - no separately-typed name/
# DOB literals anywhere else in this file.
PROFILE_SCENARIOS = {
    "matching_profile": {
        "profile": {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB},
        "expect_passed": True,
        "expect_issue_substrings": [],
    },
    "matching_profile_reordered_case_name": {
        "profile": {"name": REORDERED_CASE_NAME, "dob": CANDIDATE_TRUE_DOB},
        "expect_passed": True,
        "expect_issue_substrings": [],
    },
    "name_mismatch_only": {
        "profile": {"name": MISMATCHED_NAME, "dob": CANDIDATE_TRUE_DOB},
        "expect_passed": False,
        "expect_issue_substrings": ["does not match candidate profile"],
    },
    "dob_mismatch_only": {
        "profile": {"name": CANDIDATE_TRUE_NAME, "dob": MISMATCHED_DOB},
        "expect_passed": False,
        "expect_issue_substrings": ["DOB on document"],
    },
    "name_and_dob_both_mismatch": {
        # Previously untested: BOTH checks fail at once - issues list
        # should contain two separate entries, not just one.
        "profile": {"name": MISMATCHED_NAME, "dob": MISMATCHED_DOB},
        "expect_passed": False,
        "expect_issue_substrings": ["does not match candidate profile", "DOB on document"],
    },
    "no_profile_fields_supplied": {
        # name/dob missing from the profile entirely - checks should be
        # SKIPPED (nothing to compare against), not treated as a mismatch.
        "profile": {},
        "expect_passed": True,
        "expect_issue_substrings": [],
    },
}


async def get_real_structured(filename: str):
    path = os.path.join(TEST_DOCS_DIR, filename)
    if not os.path.exists(path):
        return None, None

    file_meta = {"originalName": filename, "storedPath": path}
    ocr_result = extract_text(file_meta)
    classification = classify_document(file_meta, ocr_text=ocr_result["rawText"])
    structured = await structured_extraction(classification["docType"], ocr_result["rawText"])
    return classification, structured


def _check_scenario(structured, scenario_name, scenario):
    result = run_document_rules(structured, scenario["profile"])
    passed_ok = result["passed"] == scenario["expect_passed"]
    issues_ok = all(
        any(substr in issue for issue in result["issues"]) for substr in scenario["expect_issue_substrings"]
    )
    # If we expect it to pass, there should be zero issues at all -
    # catches an unexpected issue sneaking in even when passed==True.
    no_unexpected_issues = (not scenario["expect_issue_substrings"]) == (len(result["issues"]) == 0) \
        if scenario["expect_passed"] else True

    scenario_passed = passed_ok and issues_ok and no_unexpected_issues
    marker = "PASS" if scenario_passed else "FAIL"
    print(f"    [{marker}] scenario={scenario_name}")
    print(f"        expected passed={scenario['expect_passed']}, got passed={result['passed']}")
    print(f"        issues={result['issues']}")
    return scenario_passed


async def run_id_document_scenarios(filename: str):
    classification, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    print(f"  {filename}  (classified as {classification['docType']})")
    print(f"    structured (real, from stage3): {structured}")

    all_passed = True
    for scenario_name, scenario in PROFILE_SCENARIOS.items():
        all_passed = _check_scenario(structured, scenario_name, scenario) and all_passed

    # Guard-scoping check: a PAN_CARD structured dict should NEVER produce
    # an Aadhaar-length issue, since that block is gated on
    # docType == "AADHAAR_CARD" specifically. Verified across every
    # scenario's issues just run above.
    if structured.get("docType") == "PAN_CARD":
        for scenario_name, scenario in PROFILE_SCENARIOS.items():
            result = run_document_rules(structured, scenario["profile"])
            has_aadhaar_issue = any("Aadhaar number" in issue for issue in result["issues"])
            ok = not has_aadhaar_issue
            all_passed = all_passed and ok
            marker = "PASS" if ok else "FAIL"
            print(f"    [{marker}] PAN_CARD never raises an Aadhaar-length issue (scenario={scenario_name})")

    print(f"    {'ALL SCENARIOS PASS' if all_passed else 'SOME SCENARIOS FAILED'}\n")
    return all_passed


async def run_aadhaar_shape_variants(filename: str):
    """
    Aadhaar-length validation can't be exercised by the clean sample
    document (its Aadhaar is always a valid 12 digits). To test the
    invalid-shape branch, we take a COPY of the real structured dict and
    mutate only the 'aadhaar' field - everything else stays exactly as
    stage3 produced it.
    """
    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found (aadhaar shape variants)\n")
        return None

    real_aadhaar = structured.get("aadhaar")
    print(f"  Aadhaar shape variants (base file={filename}, real aadhaar={real_aadhaar!r})")

    variants = {
        "valid_12_digits (control, from real doc)": {
            "aadhaar": real_aadhaar,
            "expect_issue": False,
        },
        "missing_entirely (simulated extraction miss)": {
            "aadhaar": None,
            "expect_issue": True,
        },
        "too_few_digits (simulated OCR miss)": {
            "aadhaar": "2345 1234",
            "expect_issue": True,
        },
        "too_many_digits (simulated OCR miss)": {
            "aadhaar": (real_aadhaar or "234512348123") + "99",
            "expect_issue": True,
        },
    }

    all_passed = True
    for variant_name, variant in variants.items():
        mutated = copy.deepcopy(structured)
        mutated["aadhaar"] = variant["aadhaar"]

        result = run_document_rules(mutated, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})
        has_aadhaar_issue = any("Aadhaar number" in issue for issue in result["issues"])
        ok = has_aadhaar_issue == variant["expect_issue"]
        all_passed = all_passed and ok

        marker = "PASS" if ok else "FAIL"
        print(f"    [{marker}] {variant_name}: aadhaar={variant['aadhaar']!r} -> expect_issue={variant['expect_issue']}, got_issue={has_aadhaar_issue}")

    print(f"    {'ALL PASS' if all_passed else 'SOME FAILED'}\n")
    return all_passed


async def run_missing_dob_variant(filename: str):
    """
    If stage3 ever fails to extract a DOB at all (key present but None,
    or key missing entirely), the DOB-mismatch check should be SKIPPED,
    not falsely flagged - `profile_dob and doc_dob` in the rule engine is
    only truthy when BOTH sides have a real value. Built from a real
    structured dict with the 'dob' key removed.
    """
    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found (missing-DOB variant)\n")
        return None

    mutated = copy.deepcopy(structured)
    mutated.pop("dob", None)  # simulate stage3 not finding a DOB at all

    # Even with a deliberately WRONG profile DOB, no DOB issue should
    # appear, since the document side has nothing to compare against.
    result = run_document_rules(mutated, {"name": CANDIDATE_TRUE_NAME, "dob": MISMATCHED_DOB})
    has_dob_issue = any("DOB on document" in issue for issue in result["issues"])
    ok = not has_dob_issue

    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] missing 'dob' key on {filename} -> DOB check correctly skipped (issues={result['issues']})\n")
    return ok


async def run_non_id_document_check(filename: str):
    """Non-ID documents only hit the generic 'was a name detected' check."""
    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    result = run_document_rules(structured, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})
    name_was_detected = structured.get("name") is not None
    ok = result["passed"] == name_was_detected

    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {filename}: name_detected={name_was_detected}, passed={result['passed']}, issues={result['issues']}\n")
    return ok


async def run_missing_name_variant(filename: str):
    """
    The generic 'Could not detect candidate name on document' check
    applies regardless of docType. Simulated by removing 'name' from a
    real structured dict (name extraction can fail on a blurry scan even
    though this clean sample never triggers it naturally).
    """
    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found (missing-name variant)\n")
        return None

    mutated = copy.deepcopy(structured)
    mutated["name"] = None

    result = run_document_rules(mutated, {"name": CANDIDATE_TRUE_NAME, "dob": CANDIDATE_TRUE_DOB})
    has_name_issue = any("Could not detect candidate name" in issue for issue in result["issues"])
    ok = has_name_issue and not result["passed"]

    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {filename} with name=None -> issue raised, passed=False (issues={result['issues']})\n")
    return ok


async def run_default_profile_argument_test(filename: str):
    """
    `run_document_rules(structured)` with candidate_profile omitted
    entirely should behave identically to passing candidate_profile={}
    or candidate_profile=None - exercises the
    `candidate_profile = candidate_profile or {}` default branch
    specifically. Uses a REAL structured dict from stage3 (same as
    every other test in this file), not a hand-crafted one.
    """
    print("-" * 70)
    print("UNIT TEST: candidate_profile default argument (omitted vs {} vs None)")
    print("-" * 70)

    _, structured = await get_real_structured(filename)
    if structured is None:
        print(f"  [SKIP] {filename} not found\n")
        return None

    print(f"  base file={filename}, structured (real, from stage3): {structured}\n")

    result_omitted = run_document_rules(structured)  # no second arg at all
    result_explicit_empty = run_document_rules(structured, {})
    result_explicit_none = run_document_rules(structured, None)

    ok = result_omitted == result_explicit_empty == result_explicit_none
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] omitted={result_omitted}")
    print(f"      explicit_empty={result_explicit_empty}")
    print(f"      explicit_none={result_explicit_none}\n")
    return ok


def run_name_matching_unit_tests():
    print("-" * 70)
    print("UNIT TESTS: _names_roughly_match")
    print("-" * 70)

    cases = [
        (CANDIDATE_TRUE_NAME, CANDIDATE_TRUE_NAME.upper(), True),        # case-insensitive
        (CANDIDATE_TRUE_NAME, REORDERED_CASE_NAME, True),                # word order + case both differ
        (CANDIDATE_TRUE_NAME, "Rahul K Sharma", False),                  # abbreviated middle name - not a match
        (CANDIDATE_TRUE_NAME, MISMATCHED_NAME, False),                   # different name entirely
        (CANDIDATE_TRUE_NAME, f"   {CANDIDATE_TRUE_NAME.lower()}   ", True),  # extra whitespace, lowercase
    ]

    all_passed = True
    for name_a, name_b, expected in cases:
        got = _names_roughly_match(name_a, name_b)
        passed = got == expected
        all_passed = all_passed and passed
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] _names_roughly_match({name_a!r}, {name_b!r}) -> expected={expected}, got={got}")

    print(f"  {'ALL PASS' if all_passed else 'SOME FAILED'}\n")
    return all_passed


def run_mandatory_documents_unit_tests():
    print("-" * 70)
    print("UNIT TESTS: check_mandatory_documents")
    print("-" * 70)

    cases = [
        {"name": "all_mandatory_present", "uploaded": list(MANDATORY_DOC_TYPES),
         "expect_complete": True, "expect_missing": []},
        {"name": "one_missing", "uploaded": [dt for dt in MANDATORY_DOC_TYPES if dt != "CANCELLED_CHEQUE"],
         "expect_complete": False, "expect_missing": ["CANCELLED_CHEQUE"]},
        {"name": "nothing_uploaded", "uploaded": [],
         "expect_complete": False, "expect_missing": list(MANDATORY_DOC_TYPES)},
        {"name": "extra_non_mandatory_docs_dont_count",
         "uploaded": list(MANDATORY_DOC_TYPES) + ["PASSPORT_PHOTO", "GAP_AFFIDAVIT"],
         "expect_complete": True, "expect_missing": []},
        {"name": "duplicate_uploads_of_same_type_dont_break_check",
         "uploaded": list(MANDATORY_DOC_TYPES) + ["PAN_CARD", "PAN_CARD"],
         "expect_complete": True, "expect_missing": []},
    ]

    all_passed = True
    for case in cases:
        result = check_mandatory_documents(case["uploaded"])
        passed = (
            result["complete"] == case["expect_complete"]
            and sorted(result["missing"]) == sorted(case["expect_missing"])
        )
        all_passed = all_passed and passed
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {case['name']}")
        print(f"      expected complete={case['expect_complete']}, missing={case['expect_missing']}")
        print(f"      got      complete={result['complete']}, missing={result['missing']}\n")

    print(f"  {'ALL PASS' if all_passed else 'SOME FAILED'}\n")
    return all_passed


async def main():
    print(f"TEST_DOCS_DIR = {TEST_DOCS_DIR}")
    print(f"Candidate identity used throughout: name={CANDIDATE_TRUE_NAME!r}, dob={CANDIDATE_TRUE_DOB!r}\n")
    print("=" * 70)
    print("PART 1: PAN/AADHAAR structured docs (real, from stage3) x profile scenarios")
    print("=" * 70)
    id_results = []
    for filename in ID_DOC_FILES:
        result = await run_id_document_scenarios(filename)
        if result is not None:
            id_results.append((f"scenarios:{filename}", result))

    print("=" * 70)
    print("PART 2: Aadhaar shape validation (real dict, aadhaar field mutated)")
    print("=" * 70)
    aadhaar_results = []
    for filename in ["aadhaar_card.jpg", "aadhaar_card.pdf"]:
        result = await run_aadhaar_shape_variants(filename)
        if result is not None:
            aadhaar_results.append((f"aadhaar_shape:{filename}", result))

    print("=" * 70)
    print("PART 3: Missing DOB field (real dict, dob key removed) -> check skipped, not flagged")
    print("=" * 70)
    dob_results = []
    for filename in ID_DOC_FILES:
        result = await run_missing_dob_variant(filename)
        if result is not None:
            dob_results.append((f"missing_dob:{filename}", result))

    print("=" * 70)
    print("PART 4: Non-ID documents - generic name-detected check only")
    print("=" * 70)
    non_id_results = []
    for filename in NON_ID_DOC_FILES:
        result = await run_non_id_document_check(filename)
        if result is not None:
            non_id_results.append((f"non_id:{filename}", result))

    print("=" * 70)
    print("PART 5: Missing name field (real dict, name set to None) -> generic check fires")
    print("=" * 70)
    missing_name_results = []
    for filename in ID_DOC_FILES + NON_ID_DOC_FILES:
        result = await run_missing_name_variant(filename)
        if result is not None:
            missing_name_results.append((f"missing_name:{filename}", result))

    default_arg_passed = await run_default_profile_argument_test(ID_DOC_FILES[0])
    name_match_passed = run_name_matching_unit_tests()
    mandatory_docs_passed = run_mandatory_documents_unit_tests()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_groups = (
        id_results + aadhaar_results + dob_results + non_id_results + missing_name_results
        + [("default_profile_argument", default_arg_passed)]
        + [("_names_roughly_match unit tests", name_match_passed)]
        + [("check_mandatory_documents unit tests", mandatory_docs_passed)]
    )
    for name, passed in all_groups:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    failed = sum(1 for _, passed in all_groups if not passed)
    print(f"\n{len(all_groups) - failed}/{len(all_groups)} test groups fully passed")


if __name__ == "__main__":
    asyncio.run(main())