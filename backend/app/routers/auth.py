"""
Auth routes: register / login / me
Port of controllers/authController.js + routes/authRoutes.js
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth import hash_password, require_auth, sign_token, verify_password
from app.db import read_db, write_db
from app.models import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/register", status_code=201)
def register(body: RegisterRequest):
    if not body.name or not body.email or not body.password:
        raise HTTPException(status_code=400, detail="name, email and password are required")

    db = read_db()
    existing = next((u for u in db["users"] if u["email"].lower() == body.email.lower()), None)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    password_hash = hash_password(body.password)
    user = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "email": body.email,
        "passwordHash": password_hash,
        "role": body.role,
        "createdAt": _now(),
    }
    db["users"].append(user)

    # If registering as a candidate, auto-create their candidate profile
    if body.role == "candidate":
        db["candidates"].append(
            {
                "id": str(uuid.uuid4()),
                "userId": user["id"],
                "name": body.name,
                "email": body.email,
                "position": body.position or "",
                "department": body.department or "",
                "dob": body.dob or "",
                "createdAt": _now(),
            }
        )

    write_db(db)

    token = sign_token(user)
    return {
        "token": token,
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
    }


@router.post("/login")
def login(body: LoginRequest):
    if not body.email or not body.password:
        raise HTTPException(status_code=400, detail="email and password are required")

    db = read_db()
    user = next((u for u in db["users"] if u["email"].lower() == body.email.lower()), None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(body.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = sign_token(user)
    return {
        "token": token,
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
    }


@router.get("/me")
def me(current_user: dict = Depends(require_auth)):
    db = read_db()
    user = next((u for u in db["users"] if u["id"] == current_user["id"]), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}
