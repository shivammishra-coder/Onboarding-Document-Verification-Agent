"""
Auth utilities: password hashing, JWT sign/verify, and FastAPI dependencies
that mirror the original Express middleware (`requireAuth`, `requireRole`).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import JWT_ALGORITHM, JWT_EXPIRES_IN_HOURS, JWT_SECRET

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def sign_token(user: dict) -> str:
    """user: { id, email, role, name }"""
    payload = {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_IN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """
    Verifies the Bearer token on the request and returns the decoded
    payload ({ id, email, role, name }), mirroring req.user in the JS version.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_role(*roles: str):
    """
    Restricts a route to specific roles, e.g. Depends(require_role("hr")).
    Must be combined with require_auth (it depends on it internally).
    """

    def dependency(user: dict = Depends(require_auth)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return dependency
