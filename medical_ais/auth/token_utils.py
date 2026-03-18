"""
JWT creation / verification + bcrypt password hashing.
All cryptographic logic lives here — nowhere else.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(
    data: dict[str, Any],
    secret: str,
    expires_minutes: int = 15,
) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload.update({"exp": expire, "type": "access"})
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(
    data: dict[str, Any],
    secret: str,
    expires_days: int = 7,
) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)
    payload.update({"exp": expire, "type": "refresh"})
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.
    Raises JWTError on invalid / expired tokens.
    """
    return jwt.decode(token, secret, algorithms=["HS256"])
