import os
import sys
import glob
import asyncio
import json
from typing import List, Dict

# --- PATH FIX ---
# Forces Python to recognize your app folder structure
backend_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.pipeline.orchestrator import OnboardingOrchestrator

# Point this to the folder containing your test documents
DOCS_DIR = os.path.join(backend_root, "app", "invalid_test_documents")  

def print_audit_trail(result: Dict):
    """Formats the final pipeline output into a clean, readable dashboard."""
    print(f"\n{'='*80}")
    print("🚀 END-TO-END PIPELINE EXECUTION COMPLETE")
    print(f"{'='*80}")
    
    # 1. High-Level Summary
    status = result.get("status", "UNKNOWN")
    status_icon = "🟢" if status == "VERIFIED" else "🟡" if status == "PENDING_DOCUMENTS" else "🔴"
    
    print("\n▶ FINAL DECISION ENGINE STATUS")
    print(f"  - STATUS  : {status_icon} {status}")
    print(f"  - SUMMARY : {result.get('summary')}")
    print(f"  - DOCS    : Processed {result['pipeline_metrics'].get('total_documents_processed')} files.")
    
        # 2. NEW: Per-document classification + extraction breakdown
    print("\n▶ PER-DOCUMENT CLASSIFICATION & EXTRACTION")
    for doc in result.get("document_extractions", []):
        filename = doc.get("originalName", "?")
        doc_type = doc.get("document_type", "UNKNOWN")
        confidence = doc.get("confidence_score", 0.0)
        extracted = doc.get("extracted_data", {}) or {}
        shape_warnings = doc.get("shape_warnings", [])
        error = doc.get("error")

        print(f"\n  📄 {filename}")
        print(f"     document_type    : {doc_type}  (confidence: {confidence})")

        if error:
            print(f"     ❌ error         : {error}")
            continue

        if not extracted:
            print("     (no fields expected/extracted for this type)")
        else:
            for field_name, value in extracted.items():
                if value is None or value == "" or value == []:
                    print(f"     ❌ {field_name:<28}: MISSING (null)")
                else:
                    print(f"     ✅ {field_name:<28}: {value}")

        if shape_warnings:
            print("     ⚠️  shape_warnings:")
            for w in shape_warnings:
                print(f"        - {w}")

    # 2. Action Items (Failures)
    action_items = result.get("action_items", [])
    if action_items:
        print("\n▶ REQUIRED ACTION ITEMS (FAILURES):")
        for item in action_items:
            print(f"    🚩 {item}")

    # 3. AI Context Notes
    notes = result.get("hr_context_notes", [])
    if notes:
        print("\n▶ AI AUDITOR NOTES (CONTEXT):")
        for note in notes:
            print(f"    💡 {note}")
            
    # 4. Optional: Print the raw JSON block for debugging the extracted fields
    print(f"\n{'='*80}")
    print("RAW PIPELINE OUTPUT (JSON):")
    # Uncomment the line below if you want to see the massive JSON blob of all extracted fields
    print(json.dumps(result, indent=2))
    print(f"{'='*80}\n")


async def main():
    print(f"\nScanning for documents in: {DOCS_DIR}")
    
    
# Grab all supported files (PDFs and Images)
    supported_extensions = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf")
    
    # Use a set to automatically prevent duplicate file paths on Windows
    unique_file_paths = set()
    for ext in supported_extensions:
        unique_file_paths.update(glob.glob(os.path.join(DOCS_DIR, ext)))
        unique_file_paths.update(glob.glob(os.path.join(DOCS_DIR, ext.upper())))
        
    # Convert back to a list
    file_paths = list(unique_file_paths)
        
    if not file_paths:
        print(f"⚠️ No documents found in {DOCS_DIR}. Please add some test files and try again.")
        return

    # Construct the file payload expected by Orchestrator
    uploaded_files: List[Dict[str, str]] = []
    for path in file_paths:
        uploaded_files.append({
            "originalName": os.path.basename(path),
            "storedPath": path
        })
        print(f"  📎 Loaded: {os.path.basename(path)}")

   

    print("\n⚙️ Firing up the 5-Step Pipeline... (This may take a few moments depending on Groq API limits)")
    
    # Initialize and run the pipeline
    orchestrator = OnboardingOrchestrator()
    final_result = await orchestrator.run_pipeline(uploaded_files)

    # Print the beautiful summary
    print_audit_trail(final_result)


if __name__ == "__main__":
    # Windows fix for asyncio event loops if running older Python versions
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main())