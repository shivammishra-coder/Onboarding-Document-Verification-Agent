"""Pydantic request/response schemas."""
from typing import Literal, Optional

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: Literal["hr", "candidate"]
    position: Optional[str] = ""
    department: Optional[str] = ""
    dob: Optional[str] = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class UpdateCandidateRequest(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None


class ReviewRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT", "REQUEST_REUPLOAD"]
    notes: Optional[str] = ""
