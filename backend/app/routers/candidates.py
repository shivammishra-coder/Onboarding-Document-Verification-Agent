"""
Candidate routes: list (HR), get own profile, update own profile, get by id (HR)
Port of controllers/candidateController.js + routes/candidateRoutes.js
"""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_auth, require_role
from app.db import read_db, write_db
from app.models import UpdateCandidateRequest

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


@router.get("")
def list_candidates(user: dict = Depends(require_role("hr"))):
    db = read_db()
    candidates = []
    for c in db["candidates"]:
        docs = [d for d in db["documents"] if d["candidateId"] == c["id"]]
        candidates.append({**c, "documentCount": len(docs)})
    return candidates


@router.get("/me")
def get_my_candidate_profile(user: dict = Depends(require_role("candidate"))):
    db = read_db()
    candidate = next((c for c in db["candidates"] if c["userId"] == user["id"]), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
    return candidate


@router.put("/me")
def update_my_candidate_profile(body: UpdateCandidateRequest, user: dict = Depends(require_role("candidate"))):
    db = read_db()
    idx = next((i for i, c in enumerate(db["candidates"]) if c["userId"] == user["id"]), -1)
    if idx == -1:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    updates = {k: v for k, v in body.model_dump().items() if v}
    db["candidates"][idx] = {**db["candidates"][idx], **updates}
    write_db(db)
    return db["candidates"][idx]


@router.get("/{candidate_id}")
def get_candidate_by_id(candidate_id: str, user: dict = Depends(require_role("hr"))):
    db = read_db()
    candidate = next((c for c in db["candidates"] if c["id"] == candidate_id), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate
