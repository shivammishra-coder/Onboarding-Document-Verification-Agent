"""
Document routes: upload, list mine, list all (HR), get by id, review (HR),
reupload. Port of controllers/documentController.js + routes/documentRoutes.js
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth import require_auth, require_role
from app.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES, UPLOAD_DIR
from app.db import read_db, write_db
from app.models import ReviewRequest
from app.pipeline.orchestrator import run_pipeline

router = APIRouter(prefix="/api/documents", tags=["documents"])

os.makedirs(UPLOAD_DIR, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _save_upload(file: UploadFile) -> dict:
    """
    Validates and persists an uploaded file to disk, mirroring the multer
    config in routes/documentRoutes.js (allowed extensions + 15MB limit).
    Returns { originalName, storedPath, size }.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, PNG and JPG files are allowed")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 15MB size limit")

    stored_name = f"{uuid.uuid4()}{ext}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    with open(stored_path, "wb") as f:
        f.write(contents)

    return {"originalName": file.filename, "storedPath": stored_path, "size": len(contents)}


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    declaredDocType: Optional[str] = Form(None),
    user: dict = Depends(require_role("candidate")),
):
    db = read_db()
    candidate = next((c for c in db["candidates"] if c["userId"] == user["id"]), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    saved = await _save_upload(file)

    existing_hashes = [
        d.get("pipelineResult", {}).get("fraudResult", {}).get("hash")
        for d in db["documents"]
    ]
    existing_hashes = [h for h in existing_hashes if h]

    file_meta = {
        "originalName": saved["originalName"],
        "storedPath": saved["storedPath"],
        "sizeBytes": saved["size"],
        "declaredDocType": declaredDocType,
    }

    pipeline_result = await run_pipeline(
        file_meta,
        {"name": candidate["name"], "dob": candidate.get("dob")},
        existing_hashes,
    )

    document = {
        "id": str(uuid.uuid4()),
        "candidateId": candidate["id"],
        "originalName": saved["originalName"],
        "storedPath": saved["storedPath"],
        "docType": pipeline_result["classification"]["docType"],
        "status": pipeline_result["decision"]["outcome"],  # VERIFIED | NEEDS_ATTENTION | REJECTED (pre-HITL)
        "hitlStatus": "PENDING",  # every document still needs Human-in-the-Loop final check
        "pipelineResult": pipeline_result,
        "createdAt": _now(),
        "updatedAt": _now(),
    }

    db["documents"].append(document)
    write_db(db)

    return document


@router.get("/mine")
def list_my_documents(user: dict = Depends(require_role("candidate"))):
    db = read_db()
    candidate = next((c for c in db["candidates"] if c["userId"] == user["id"]), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
    return [d for d in db["documents"] if d["candidateId"] == candidate["id"]]


@router.get("")
def list_all_documents(status: Optional[str] = None, user: dict = Depends(require_role("hr"))):
    db = read_db()
    docs = db["documents"]
    if status:
        docs = [d for d in docs if d["status"] == status]

    enriched = []
    for d in docs:
        candidate = next((c for c in db["candidates"] if c["id"] == d["candidateId"]), None)
        enriched.append(
            {
                **d,
                "candidateName": candidate["name"] if candidate else None,
                "candidateEmail": candidate["email"] if candidate else None,
            }
        )

    enriched.sort(key=lambda d: d["createdAt"], reverse=True)
    return enriched


@router.post("/{document_id}/review")
def review_document(document_id: str, body: ReviewRequest, user: dict = Depends(require_role("hr"))):
    db = read_db()
    idx = next((i for i, d in enumerate(db["documents"]) if d["id"] == document_id), -1)
    if idx == -1:
        raise HTTPException(status_code=404, detail="Document not found")

    status_map = {
        "APPROVE": "VERIFIED",
        "REJECT": "REJECTED",
        "REQUEST_REUPLOAD": "NEEDS_ATTENTION",
    }

    db["documents"][idx]["hitlStatus"] = "COMPLETED"
    db["documents"][idx]["status"] = status_map[body.decision]
    db["documents"][idx]["updatedAt"] = _now()

    db["reviews"].append(
        {
            "id": str(uuid.uuid4()),
            "documentId": db["documents"][idx]["id"],
            "reviewerId": user["id"],
            "decision": body.decision,
            "notes": body.notes or "",
            "createdAt": _now(),
        }
    )

    write_db(db)

    # Final step per the flow diagram: "Candidate notified" (email + dashboard update).
    # Wire up a real email provider (SES/SendGrid) here; logging as a stand-in.
    print(
        f"[NOTIFY] Candidate {db['documents'][idx]['candidateId']} notified: "
        f"document {db['documents'][idx]['id']} -> {db['documents'][idx]['status']}"
    )

    return db["documents"][idx]


@router.post("/{document_id}/reupload")
async def reupload_document(
    document_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_role("candidate")),
):
    db = read_db()
    candidate = next((c for c in db["candidates"] if c["userId"] == user["id"]), None)
    doc_idx = next(
        (i for i, d in enumerate(db["documents"]) if d["id"] == document_id and candidate and d["candidateId"] == candidate["id"]),
        -1,
    )
    if doc_idx == -1:
        raise HTTPException(status_code=404, detail="Document not found")

    saved = await _save_upload(file)

    # best-effort cleanup of the old file
    try:
        os.unlink(db["documents"][doc_idx]["storedPath"])
    except OSError:
        pass

    existing_hashes = [
        d.get("pipelineResult", {}).get("fraudResult", {}).get("hash")
        for d in db["documents"]
        if d["id"] != document_id
    ]
    existing_hashes = [h for h in existing_hashes if h]

    file_meta = {
        "originalName": saved["originalName"],
        "storedPath": saved["storedPath"],
        "sizeBytes": saved["size"],
        "declaredDocType": db["documents"][doc_idx]["docType"],
    }

    pipeline_result = await run_pipeline(
        file_meta,
        {"name": candidate["name"], "dob": candidate.get("dob")},
        existing_hashes,
    )

    db["documents"][doc_idx] = {
        **db["documents"][doc_idx],
        "originalName": saved["originalName"],
        "storedPath": saved["storedPath"],
        "docType": pipeline_result["classification"]["docType"],
        "status": pipeline_result["decision"]["outcome"],
        "hitlStatus": "PENDING",
        "pipelineResult": pipeline_result,
        "updatedAt": _now(),
    }

    write_db(db)
    return db["documents"][doc_idx]


# NOTE: this catch-all id route must stay LAST among GET routes on this router
# so it doesn't shadow /mine, "" (list), etc. (mirrors ordering in the Express version).
@router.get("/{document_id}")
def get_document_by_id(document_id: str, user: dict = Depends(require_auth)):
    db = read_db()
    doc = next((d for d in db["documents"] if d["id"] == document_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    candidate = next((c for c in db["candidates"] if c["id"] == doc["candidateId"]), None)
    return {
        **doc,
        "candidateName": candidate["name"] if candidate else None,
        "candidateEmail": candidate["email"] if candidate else None,
    }
