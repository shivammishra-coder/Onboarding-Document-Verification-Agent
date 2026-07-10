"""
Lightweight JSON-file database.

Why not a real DB in this starter?
------------------------------------
To keep this project runnable anywhere with zero external services
(no Postgres/Mongo server to stand up), we persist everything to a single
JSON file on disk. Reads/writes are guarded by a simple in-process lock,
which is fine for a demo / internal-tool scale app.

TO GO TO PRODUCTION: replace the functions below with real queries
(Postgres via SQLAlchemy, or MongoDB via Motor/PyMongo). Every place in
the codebase that touches data goes through this module, so that's the
only file you'd need to rewrite.
"""
import json
import os
import threading
from typing import Any, Dict

from app.config import DB_FILE, DATA_DIR

DEFAULT_DATA: Dict[str, Any] = {
    "users": [],       # { id, name, email, passwordHash, role: 'hr' | 'candidate', createdAt }
    "candidates": [],  # { id, userId, name, email, position, department, createdAt }
    "documents": [],   # { id, candidateId, originalName, storedPath, docType, status, pipelineResult, createdAt, updatedAt }
    "reviews": [],     # { id, documentId, reviewerId, decision, notes, createdAt }
}

_lock = threading.Lock()


def _ensure_db_file() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_DATA, f, indent=2)


def read_db() -> Dict[str, Any]:
    with _lock:
        _ensure_db_file()
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt file safety net - reset rather than crash the server
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_DATA, f, indent=2)
            return json.loads(json.dumps(DEFAULT_DATA))


def write_db(data: Dict[str, Any]) -> None:
    with _lock:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
