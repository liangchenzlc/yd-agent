from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status

from app.config.settings import get_settings
from app.web.db import db


TOKEN_TTL_HOURS = 24
JWT_ALGORITHM = "HS256"


def _secret() -> str:
    key = get_settings().web_secret_key
    if not key:
        raise RuntimeError("WEB_SECRET_KEY is not configured. Set it in .env before starting the server.")
    return key


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _, salt, expected = password_hash.split("$", 2)
    except ValueError:
        return False
    actual = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)


def create_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "tenant_id": user.get("tenant_id", "default"),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def get_current_user(
    authorization: str = Header(default=""),
    access_token: str = Cookie(default=""),
) -> dict[str, Any]:
    scheme, _, bearer_token = authorization.partition(" ")
    token = bearer_token if scheme.lower() == "bearer" and bearer_token else access_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    payload = decode_token(token)
    user = db.get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.get("enabled", 1):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    return user


def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") not in {"admin", "super_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def ensure_default_admin() -> None:
    if db.get_user_by_username("admin"):
        return
    db.create_user("admin", hash_password("admin"), role="admin")


def _b64url_json(value: dict[str, Any]) -> str:
    return _b64url(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
