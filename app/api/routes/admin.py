from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.agent.stats.usage_tracker import get_daily_stats
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
from app.runtime import AgentRuntime
from app.services.documents import delete_document, ingest_document, list_documents
from app.web.auth import (
    get_current_user,
    hash_password,
    require_admin,
    require_super_admin,
)
from app.web.db import db
from app.web.schemas import (
    AdminCreateRequest,
    AdminUpdateRequest,
    DataSourceRequest,
    PasswordResetRequest,
    TenantCreateRequest,
    TenantUpdateRequest,
    UserCreateRequest,
    UserUpdateRequest,
)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/json",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
MAX_FILE_SIZE = 50 * 1024 * 1024


def _validate_upload(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file.content_type}。允许: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )
    head = file.file.read(8192)
    if len(head) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")
    _check_magic_bytes(head, file.content_type)
    remaining = file.file.read()
    total = len(head) + len(remaining)
    if total > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大 ({total / 1024 / 1024:.1f} MB)，最大允许 {MAX_FILE_SIZE / 1024 / 1024:.0f} MB",
        )
    file.file.seek(0)


def _check_magic_bytes(head: bytes, mime: str) -> None:
    magic_map = {
        "application/pdf": [(b"%PDF", 0)],
        "application/msword": [(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0)],
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
            (b"PK\x03\x04", 0),
        ],
    }
    checks = magic_map.get(mime, [])
    if not checks:
        return
    for magic_bytes, offset in checks:
        if head[offset:offset + len(magic_bytes)] != magic_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件类型不匹配（预期 {mime}，但内容签名不一致）",
            )


router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================
# 租户管理 — 仅 super_admin
# ============================================================


@router.get("/tenants")
def list_tenants(user: dict = Depends(require_super_admin)) -> list[dict]:
    return db.list_tenants()


@router.post("/tenants")
def create_tenant(payload: TenantCreateRequest, user: dict = Depends(require_super_admin)) -> dict:
    if db.get_tenant(payload.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="租户 ID 已存在")
    return db.create_tenant(payload.id, payload.name, payload.config)


@router.patch("/tenants/{tenant_id}")
def update_tenant(tenant_id: str, payload: TenantUpdateRequest,
                  user: dict = Depends(require_super_admin)) -> dict:
    if not db.get_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="租户不存在")
    updated = db.update_tenant(tenant_id, name=payload.name, config=payload.config)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="租户不存在")
    return updated


@router.delete("/tenants/{tenant_id}")
def delete_tenant(tenant_id: str, user: dict = Depends(require_super_admin)) -> dict:
    if not db.delete_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="租户不存在")
    return {"deleted": tenant_id}


# ============================================================
# Admin 账号管理 — 仅 super_admin（创建指定租户的 admin）
# ============================================================


@router.get("/admin-users")
def list_admin_users(user: dict = Depends(require_super_admin)) -> list[dict]:
    return db.list_users(role="admin")


@router.post("/admin-users")
def create_admin(payload: AdminCreateRequest, user: dict = Depends(require_super_admin)) -> dict:
    if not db.get_tenant(payload.tenant_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"租户 {payload.tenant_id} 不存在")
    if db.get_user_by_username(payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    try:
        created = db.create_user(payload.username, hash_password(payload.password),
                                 role="admin", tenant_id=payload.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _public_admin_user(created)


@router.patch("/admin-users/{user_id}")
def update_admin(user_id: int, payload: AdminUpdateRequest,
                 user: dict = Depends(require_super_admin)) -> dict:
    target = db.get_user_by_id(user_id)
    if target is None or target["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="管理员不存在")
    updated = db.update_user(user_id, enabled=payload.enabled)
    return _public_admin_user(updated)


@router.post("/admin-users/{user_id}/reset-password")
def reset_admin_password(user_id: int, payload: PasswordResetRequest,
                         user: dict = Depends(require_super_admin)) -> dict:
    target = db.get_user_by_id(user_id)
    if target is None or target["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="管理员不存在")
    db.update_user(user_id, password_hash=hash_password(payload.new_password))
    return {"detail": "密码已重置"}


@router.delete("/admin-users/{user_id}")
def delete_admin(user_id: int, user: dict = Depends(require_super_admin)) -> dict:
    target = db.get_user_by_id(user_id)
    if target is None or target["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="管理员不存在")
    db.delete_user(user_id)
    return {"deleted": user_id}


# ============================================================
# User 账号管理 — admin 管理自己租户下的 user
# ============================================================


@router.get("/users")
def list_users(user: dict = Depends(require_admin)) -> list[dict]:
    if user["role"] == "super_admin":
        return db.list_users(role="user")
    return db.list_users(role="user", tenant_id=user.get("tenant_id"))


@router.post("/users")
def create_user(payload: UserCreateRequest, user: dict = Depends(require_admin)) -> dict:
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前管理员没有关联租户")
    if db.get_user_by_username(payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    created = db.create_user(payload.username, hash_password(payload.password),
                             role="user", tenant_id=tenant_id)
    return _public_user(created)


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdateRequest,
                user: dict = Depends(require_admin)) -> dict:
    target = db.get_user_by_id(user_id)
    if target is None or target["role"] != "user":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user["role"] != "super_admin" and target.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能操作其他租户的用户")
    updated = db.update_user(user_id, enabled=payload.enabled)
    return _public_user(updated)


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, payload: PasswordResetRequest,
                        user: dict = Depends(require_admin)) -> dict:
    target = db.get_user_by_id(user_id)
    if target is None or target["role"] != "user":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user["role"] != "super_admin" and target.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能操作其他租户的用户")
    db.update_user(user_id, password_hash=hash_password(payload.new_password))
    return {"detail": "密码已重置"}


# ============================================================
# 文档管理 — admin 操作自己租户的文档
# ============================================================


@router.get("/documents")
async def documents(
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> list[dict]:
    resolved = _resolve_tenant_id(user, tenant_id)
    async with AgentRuntime(tenant_id=resolved) as runtime:
        docs = list_documents(runtime.storage_manager)
    records = {item["id"]: item for item in db.list_document_records(tenant_id=resolved)}
    tenant_names = _get_tenant_names()
    for doc in docs:
        doc.update({k: v for k, v in records.get(doc["id"], {}).items() if k not in {"id"}})
        doc.setdefault("entities", 0)
        doc.setdefault("relationships", 0)
        doc["tenant_id"] = resolved
        doc["tenant_name"] = tenant_names.get(resolved)
    return docs


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str | None = Form(None),
    user: dict = Depends(require_admin),
) -> dict:
    _validate_upload(file)
    settings = get_settings()
    resolved = _resolve_tenant_id(user, tenant_id)
    upload_dir = Path(settings.storage_dir) / "uploads" / resolved
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "document.txt").name
    target = upload_dir / f"{uuid4().hex[:8]}_{safe_name}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    async with AgentRuntime(tenant_id=resolved) as runtime:
        try:
            result = await ingest_document(runtime.storage_manager, target)
        except HTTPException:
            raise
        except Exception as e:
            target.unlink(missing_ok=True)
            logger.exception("文档处理失败")
            detail = str(e)
            if "401" in detail or "Incorrect API key" in detail or "AuthenticationError" in type(e).__name__:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="LLM/Embedding API 认证失败，请检查 .env 中的 API Key 配置")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文档处理失败: {detail}")

    db.upsert_document(
        {
            "id": result["doc_id"],
            "source": str(target),
            "uploaded_by": user["id"],
            "status": "ready" if result["ingested"] else "skipped",
            "chunks": result["total_chunks"],
        },
        tenant_id=resolved,
    )
    return result


@router.delete("/documents/{doc_id}")
async def remove_document(
    doc_id: str,
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> dict:
    resolved = _resolve_tenant_id(user, tenant_id)
    records = db.list_document_records(tenant_id=resolved)
    if not any(r["id"] == doc_id for r in records):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在或不属于当前租户")
    async with AgentRuntime(tenant_id=resolved) as runtime:
        result = await delete_document(runtime.storage_manager, doc_id)
    db.delete_document_record(doc_id)
    return result


# ============================================================
# 报表 — admin 查看自己租户的数据
# ============================================================


@router.get("/qa-logs")
def qa_logs(
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> list[dict]:
    tid = _resolve_tenant_filter(user, tenant_id)
    return _attach_tenant_name(db.list_qa_logs(limit=200, tenant_id=tid))


@router.get("/hard-cases")
def hard_cases(
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> list[dict]:
    tid = _resolve_tenant_filter(user, tenant_id)
    return _attach_tenant_name(db.list_hard_cases(limit=200, tenant_id=tid))


@router.get("/knowledge-gaps")
def knowledge_gaps(
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> list[dict]:
    tid = _resolve_tenant_filter(user, tenant_id)
    return db.list_knowledge_gaps(limit=50, tenant_id=tid)


@router.get("/usage")
async def usage(
    date: str | None = None,
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> dict:
    tid = _resolve_tenant_filter(user, tenant_id)
    return await get_daily_stats(date, tenant_id=tid)


# ============================================================
# 数据源配置 — admin 管理自己租户的数据源
# ============================================================


@router.get("/data-sources")
def get_data_source(
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> dict | None:
    tid = _resolve_tenant_filter(user, tenant_id)
    if not tid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="缺少 tenant_id")
    return db.get_data_source(tid)


@router.put("/data-sources")
def upsert_data_source(
    payload: DataSourceRequest,
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> dict:
    tid = _resolve_tenant_id(user, tenant_id)
    return db.upsert_data_source(
        tid,
        db_type=payload.db_type,
        db_host=payload.db_host,
        db_port=payload.db_port,
        db_user=payload.db_user,
        db_password=payload.db_password,
        db_database=payload.db_database,
    )


@router.delete("/data-sources")
def delete_data_source(
    tenant_id: str | None = Query(None),
    user: dict = Depends(require_admin),
) -> dict:
    tid = _resolve_tenant_id(user, tenant_id)
    if not db.delete_data_source(tid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    return {"deleted": tid}


@router.post("/data-sources/test")
def test_data_source(
    payload: DataSourceRequest,
    user: dict = Depends(require_admin),
) -> dict:
    """测试数据库连接是否可用，不存储任何配置。"""
    from app.agent.tools.database_tool import DatabaseTool

    tool = DatabaseTool(db_config={
        "type": payload.db_type,
        "host": payload.db_host,
        "port": payload.db_port,
        "user": payload.db_user,
        "password": payload.db_password,
        "database": payload.db_database,
    })
    result = tool.list_tables()
    if result.startswith("错误"):
        return {"ok": False, "message": result}
    return {"ok": True, "message": f"连接成功，{result}"}


# ============================================================
# 序列化辅助
# ============================================================


def _public_admin_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "enabled": bool(user.get("enabled", 1)),
        "tenant_id": user.get("tenant_id"),
        "created_at": user.get("created_at", ""),
    }


def _public_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "enabled": bool(user.get("enabled", 1)),
        "created_at": user.get("created_at", ""),
    }


def _resolve_tenant_id(user: dict, requested: str | None) -> str:
    """文档等需要具体租户的接口：super_admin 必须传 tenant_id，admin 用自己的。"""
    if user["role"] == "super_admin":
        if not requested:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="超级管理员必须指定 tenant_id 参数")
        return requested
    return user.get("tenant_id") or "default"


def _resolve_tenant_filter(user: dict, requested: str | None) -> str | None:
    """日志等可全局查看的接口：super_admin 可选筛选，admin 强制用自己的。"""
    if user["role"] == "super_admin":
        return requested  # None = 返回全部
    return user.get("tenant_id")


_TENANT_CACHE: tuple[float, dict[str, str]] | None = None


def _get_tenant_names() -> dict[str, str]:
    """返回 {tenant_id: name} 映射，缓存 60 秒。"""
    now = time.monotonic()
    global _TENANT_CACHE
    if _TENANT_CACHE is None or now - _TENANT_CACHE[0] > 60:
        _TENANT_CACHE = (now, {t["id"]: t["name"] for t in db.list_tenants()})
    return _TENANT_CACHE[1]


def _attach_tenant_name(records: list[dict]) -> list[dict]:
    """给记录列表附加 tenant_name。"""
    tenants = _get_tenant_names()
    for r in records:
        tid = r.get("tenant_id")
        r["tenant_name"] = tenants.get(tid) if tid else None
    return records
