import os
import json
import base64
import asyncio
import httpx
import fitz  # PyMuPDF for converting PDFs to images for the Vision model
from typing import Any, Dict, List

from app.config import GROQ_API_KEY

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
SEMANTIC_MODEL = "llama-3.3-70b-versatile"
VISION_MODEL = "llama-3.2-90b-vision-preview"

# =====================================================================
# MAIN ORCHESTRATOR FOR STEP 4
# =====================================================================
async def run_ai_cross_validation(dossier: Dict[str, Any], rule_engine_report: Dict[str, Any], candidate_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs complex semantic logic and physical visual checks on the dossier.
    """
    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY missing. Skipped AI validation."}

    # Run Semantic and Vision checks concurrently
    semantic_task = _run_semantic_analysis(dossier, rule_engine_report, candidate_profile)
    vision_task = _run_vision_analysis(dossier)
    
    semantic_result, vision_result = await asyncio.gather(semantic_task, vision_task)

    return {
        "semantic_analysis": semantic_result,
        "vision_analysis": vision_result,
        "ai_passed": semantic_result.get("passed", False) and vision_result.get("passed", False)
    }

# =====================================================================
# 1. SEMANTIC TEXT ENGINE (Entity Resolution & Chronology)
# =====================================================================
async def _run_semantic_analysis(dossier: Dict[str, Any], rule_report: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Passes the structured JSON to the 70B model to reason about timelines and entities."""
    
    prompt = f"""You are an Expert HR Auditor. Review the candidate's extracted data and the Rule Engine's initial findings.

CANDIDATE PROFILE: {json.dumps(profile)}
RULE ENGINE REPORT: {json.dumps(rule_report.get('issues', []))}
DOSSIER DATA: {json.dumps(dossier, default=str)}

PERFORM THE FOLLOWING LOGICAL CHECKS:
1. Entity Resolution: Does the Resume employer list logically match the UAN history and previous offer letters, even if spelled slightly differently (e.g., "TCS" vs "Tata Consultancy Services")?
2. Payslip Continuity: Do the extracted months in the PAYSLIP logically represent 3 consecutive months leading up to the Last Working Day?
3. Education Chronology: Look at the passing years in the MARKSHEET/DEGREE. Do they follow a logical chronological progression? Were there any mentions of 'Supplementary' or 'Backlog'?
4. Gap Reasoning: If a GAP_DECLARATION_FORM exists, is the `reason_for_gap` highly suspicious or nonsensical, or is it a standard valid reason (e.g., medical, exam prep, family)?

Respond ONLY with this exact JSON structure:
{{
    "passed": true/false,
    "anomalies": ["list of strings detailing any logical issues found"],
    "notes": ["list of strings for HR context (e.g., 'TCS successfully mapped to Tata Consultancy')"]
}}
"""
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                GROQ_API_URL,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": SEMANTIC_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                },
            )
            data = response.json()
            return json.loads(data["choices"][0]["message"]["content"])
    except Exception as e:
        return {"passed": False, "anomalies": [f"Semantic AI Failed: {str(e)}"], "notes": []}

# =====================================================================
# 2. MULTIMODAL VISION ENGINE (Signatures, Stamps, & Photos)
# =====================================================================
async def _run_vision_analysis(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """Determines which files need visual checks and routes them to the Vision API."""
    vision_tasks = []
    
    # Define which documents need which visual prompts
    VISION_ROUTER = {
        "PF_FORM_11": "Analyze this form. 1. Is the text filled out in human handwriting rather than digital typing? 2. Is there a physical wet-ink signature at the bottom?",
        "SELF_DECLARATION_FORM": "Analyze this form. Is it filled out in human handwriting, and does it contain a physical signature?",
        "PASSPORT_PHOTO": "Is this a professional headshot with a plain white background? Does it contain a clear human face?",
        "GAP_AFFIDAVIT": "Does this document appear to be printed on Indian Non-Judicial stamp paper, and does it have a visible notary stamp or seal?",
        "RESIGNATION_ACCEPTANCE": "Does this document feature an official corporate logo at the top or a visual signature at the bottom?"
    }

    for doc_type, doc_data in dossier.items():
        if doc_type in VISION_ROUTER:
            # Handle lists if multiple files of the same type exist
            docs_to_process = doc_data if isinstance(doc_data, list) else [doc_data]
            
            for doc in docs_to_process:
                file_path = doc.get("storedPath")
                if file_path and os.path.exists(file_path):
                    prompt = VISION_ROUTER[doc_type]
                    vision_tasks.append(_analyze_image_with_groq(doc_type, file_path, prompt))

    if not vision_tasks:
        return {"passed": True, "visual_flags": []}

    results = await asyncio.gather(*vision_tasks)
    
    flags = []
    for res in results:
        if not res["passed"]:
            flags.append(f"Visual check failed for {res['doc_type']}: {res['reason']}")

    return {
        "passed": len(flags) == 0,
        "visual_flags": flags
    }

async def _analyze_image_with_groq(doc_type: str, file_path: str, prompt: str) -> Dict[str, Any]:
    """Converts the file to base64 and sends it to Groq's Vision model."""
    try:
        base64_images = _convert_file_to_base64_images(file_path)
        if not base64_images:
            return {"doc_type": doc_type, "passed": False, "reason": "Could not read or convert file."}

        # For the vision model, we just send the first page to keep payload size down,
        # unless it's a multi-page document that strictly requires it.
        base64_image = base64_images[0]

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                GROQ_API_URL,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": VISION_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"{prompt} Reply only in JSON format: {{\"passed\": boolean, \"reason\": \"brief explanation\"}}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                            ]
                        }
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                },
            )
            data = response.json()
            return json.loads(data["choices"][0]["message"]["content"]) | {"doc_type": doc_type}
            
    except Exception as e:
        return {"doc_type": doc_type, "passed": False, "reason": f"Vision API error: {str(e)}"}

def _convert_file_to_base64_images(file_path: str) -> List[str]:
    """Helper: Converts images or PDFs into base64 JPEG strings for the Vision API."""
    ext = os.path.splitext(file_path)[1].lower()
    base64_images = []

    if ext == ".pdf":
        try:
            # Render PDF at 150 DPI - high enough for vision, small enough to not overload the API limit
            doc = fitz.open(file_path)
            for page_index in range(min(len(doc), 3)): # Limit to first 3 pages to avoid payload limits
                page = doc.load_page(page_index)
                pix = page.get_pixmap(dpi=150)
                base64_images.append(base64.b64encode(pix.tobytes("jpeg")).decode('utf-8'))
            doc.close()
        except Exception:
            pass
    elif ext in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with open(file_path, "rb") as img_file:
                base64_images.append(base64.b64encode(img_file.read()).decode('utf-8'))
        except Exception:
            pass

    return base64_images