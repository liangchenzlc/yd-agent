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


def _secret() -> str:
    """获取 JWT 签名密钥。

    必须从环境变量读取而非硬编码，否则所有实例使用相同密钥，
    一旦泄露可伪造任意用户的 token。
    """
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
    """PBKDF2-SHA256 密码哈希，格式：pbkdf2_sha256${salt}${digest}。

    120000 轮迭代是 OWASP 2023 年的推荐值。
    选择 PBKDF2 而非 bcrypt 的原因：Python 标准库 hashlib 原生支持，
    无需额外安装 bcrypt 依赖。
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码：使用 HMAC 比较防止时序攻击。"""
    try:
        _, salt, expected = password_hash.split("$", 2)
    except ValueError:
        return False
    actual = hash_password(password, salt).split("$", 2)[2]
    # hmac.compare_digest 是常数时间比较，防止时序攻击
    return hmac.compare_digest(actual, expected)


def create_token(user: dict[str, Any]) -> str:
    """创建 JWT token，包含用户身份和租户信息。

    JWT claims:
    - sub: 用户 ID
    - username/role/tenant_id: 用于快速鉴权，无需查数据库
    - iat/nbf/exp: 时间窗口
    - jti: 唯一 token ID，可用于 token 吊销（当前未实现吊销逻辑）
    """
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
    """解码并验证 JWT token。

    过期和签名无效时分别抛出不同的 HTTPException，
    前端可根据不同的 detail 显示不同的提示信息（"登录已过期" vs "认证失败"）。
    """
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
    """从请求中获取当前用户。

    优先使用 Authorization Header（Bearer token），
    回退到 Cookie 中的 access_token。
    这种双通道机制支持两种客户端：
    1. API 客户端使用 Bearer token
    2. Web 前端使用 Cookie（自动发送）
    """
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


def ensure_default_admin() -> None:
    """首次启动时创建默认管理员账户（admin/admin），仅限 default 租户。

    仅在数据库中尚无 admin@default 用户时执行，幂等性。
    默认密码为 "admin"，生产环境必须通过管理后台修改密码。
    """
    if db.get_user_by_username("admin", tenant_id="default"):
        return
    db.create_user("admin", hash_password("admin"), role="admin", tenant_id="default")
