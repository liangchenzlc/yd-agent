from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status

from app.config.settings import get_settings
from app.web.db import db

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 24
JWT_ALGORITHM = "HS256"

_SECRET_CACHE: str | None = None

SUPER_ADMIN_USERNAME = "super_admin"
SUPER_ADMIN_PASSWORD = "super_admin"


def _secret() -> str:
    global _SECRET_CACHE
    if _SECRET_CACHE:
        return _SECRET_CACHE
    key = get_settings().web_secret_key
    if not key:
        raise RuntimeError("WEB_SECRET_KEY is not configured. Set it in .env before starting the server.")
    if key == "change-me-in-production":
        logger.warning("WEB_SECRET_KEY 仍为默认值 'change-me-in-production'，生产环境必须修改！")
    _SECRET_CACHE = key
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
        "tenant_id": user.get("tenant_id"),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
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


def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可执行此操作")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限执行此操作")
    return user


def ensure_super_admin() -> None:
    """首次启动时创建写死的 super_admin 账号。"""
    if db.get_user_by_username(SUPER_ADMIN_USERNAME):
        return
    db.create_user(SUPER_ADMIN_USERNAME, hash_password(SUPER_ADMIN_PASSWORD),
                   role="super_admin", tenant_id=None)
    logger.info("Super admin account created: %s / %s", SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD)
