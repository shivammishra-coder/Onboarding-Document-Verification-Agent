"""
Dashboard summary route (HR only)
Port of routes/dashboardRoutes.js
"""
from fastapi import APIRouter, Depends

from app.auth import require_role
from app.db import read_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(user: dict = Depends(require_role("hr"))):
    db = read_db()
    docs = db["documents"]

    by_status = {
        "VERIFIED": len([d for d in docs if d["status"] == "VERIFIED"]),
        "NEEDS_ATTENTION": len([d for d in docs if d["status"] == "NEEDS_ATTENTION"]),
        "REJECTED": len([d for d in docs if d["status"] == "REJECTED"]),
    }

    pending_hitl = len([d for d in docs if d["hitlStatus"] == "PENDING"])

    if docs:
        total_confidence = sum((d.get("pipelineResult", {}) or {}).get("decision", {}).get("confidence", 0) for d in docs)
        avg_confidence = round(total_confidence / len(docs), 2)
    else:
        avg_confidence = 0

    return {
        "totalCandidates": len(db["candidates"]),
        "totalDocuments": len(docs),
        "byStatus": by_status,
        "pendingHitl": pending_hitl,
        "avgConfidence": avg_confidence,
    }
