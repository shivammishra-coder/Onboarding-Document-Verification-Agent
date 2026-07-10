"""
test_pipeline/print_ocr_results.py

Runs the REAL stage2 OCR extraction (extract_text) against every file in
a given folder (default: app/test_documents) and prints each result as
JSON - one file at a time to stdout, plus a combined JSON array written
to disk at the end.

Usage:
    python test_pipeline/print_ocr_results.py
    python test_pipeline/print_ocr_results.py --dir /path/to/some/docs
    python test_pipeline/print_ocr_results.py --file pan_card.jpg
    python test_pipeline/print_ocr_results.py --output my_results.json
"""
import argparse
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, BACKEND_DIR)

from app.pipeline.stage2_ocr_extraction import extract_text  # noqa: E402

DEFAULT_DOCS_DIR = os.path.join(BACKEND_DIR, "app", "valid_test_documents")
SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


def run_ocr_on_file(path: str) -> dict:
    filename = os.path.basename(path)
    file_meta = {"originalName": filename, "storedPath": path}

    started = time.time()
    try:
        result = extract_text(file_meta)
        elapsed = round(time.time() - started, 2)
        return {
            "file": filename,
            "path": path,
            "success": True,
            "elapsedSeconds": elapsed,
            "ocrConfidence": result.get("ocrConfidence"),
            "rawTextLength": len(result.get("rawText", "")),
            "rawText": result.get("rawText", ""),
        }
    except Exception as err:  # noqa: BLE001 - a bad file shouldn't kill the whole run
        elapsed = round(time.time() - started, 2)
        return {
            "file": filename,
            "path": path,
            "success": False,
            "elapsedSeconds": elapsed,
            "error": str(err),
        }


def collect_files(target_dir: str = None, single_file: str = None) -> list:
    if single_file:
        path = single_file if os.path.isabs(single_file) else os.path.join(target_dir or DEFAULT_DOCS_DIR, single_file)
        if not os.path.exists(path):
            print(f"File not found: {path}")
            return []
        return [path]

    docs_dir = target_dir or DEFAULT_DOCS_DIR
    if not os.path.isdir(docs_dir):
        print(f"Directory not found: {docs_dir}")
        return []

    files = []
    for name in sorted(os.listdir(docs_dir)):
        full_path = os.path.join(docs_dir, name)
        if os.path.isfile(full_path) and os.path.splitext(name)[1].lower() in SUPPORTED_EXTS:
            files.append(full_path)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=None, help=f"Folder of files to OCR (default: {DEFAULT_DOCS_DIR})")
    parser.add_argument("--file", default=None, help="OCR just this one file instead of a whole folder")
    parser.add_argument("--output", default="ocr_results.json", help="Where to save the combined JSON array")
    args = parser.parse_args()

    files = collect_files(target_dir=args.dir, single_file=args.file)
    if not files:
        print("No files found to process.")
        return

    print(f"Running OCR on {len(files)} file(s)...\n")

    all_results = []
    for path in files:
        result = run_ocr_on_file(path)
        all_results.append(result)

        # Pretty-print each file's result as it completes
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print()

    output_path = args.output if os.path.isabs(args.output) else os.path.join(SCRIPT_DIR, args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    succeeded = sum(1 for r in all_results if r["success"])
    print("=" * 70)
    print(f"{succeeded}/{len(all_results)} files OCR'd successfully")
    print(f"Combined results saved to: {output_path}")


if __name__ == "__main__":
    main()