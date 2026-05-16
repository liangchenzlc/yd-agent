from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.agent.stats.usage_tracker import get_daily_stats
from app.config.settings import get_settings
from app.runtime import AgentRuntime
from app.services.documents import delete_document, ingest_document, list_documents
from app.web.auth import get_current_user, hash_password
from app.web.db import db
from app.web.schemas import AdminUserCreateRequest, AdminUserUpdateRequest, TenantCreateRequest, TenantUpdateRequest

# 允许上传的文件 MIME 类型列表。
# 局限：某些 PDF 可能被错误标注为 application/octet-stream 而被拒绝，
# 但目前先严格限制，后续可根据需要扩展。
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/json",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
# 50MB 是常见云服务商的文件上传上限，超出后会影响向量嵌入的响应时间
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _validate_upload(file: UploadFile) -> None:
    """验证上传文件：Content-Type、大小、magic bytes。"""
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file.content_type}。允许: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    # 先读 8KB 用于 magic bytes 验证和空文件检测
    head = file.file.read(8192)
    if len(head) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")

    _check_magic_bytes(head, file.content_type)

    # 读取剩余部分计算总大小
    remaining = file.file.read()
    total = len(head) + len(remaining)
    if total > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大 ({total / 1024 / 1024:.1f} MB)，最大允许 {MAX_FILE_SIZE / 1024 / 1024:.0f} MB",
        )

    # 重置文件指针，让后续处理函数能重新读取完整内容
    file.file.seek(0)


def _check_magic_bytes(head: bytes, mime: str) -> None:
    """常见文档格式的 magic bytes 检查。

    防止用户修改文件扩展名或 Content-Type 绕过文件类型限制。
    对于已检查 magic bytes 的类型，如果有人改了 HTTP header 但内容不匹配，会被拒绝。
    text/plain 和 text/markdown 跳过检查，因为纯文本没有标准的 magic bytes。
    """
    magic_map = {
        "application/pdf": [(b"%PDF", 0)],
        "application/msword": [(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0)],
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
            (b"PK\x03\x04", 0),
        ],
    }
    checks = magic_map.get(mime, [])
    if not checks:
        return  # text/plain, text/markdown 等跳过

    for magic_bytes, offset in checks:
        if head[offset:offset + len(magic_bytes)] != magic_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件类型不匹配（预期 {mime}，但内容签名不一致）",
            )

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def users(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_users(tenant_id=user.get("tenant_id"))


@router.post("/users")
def create_user(payload: AdminUserCreateRequest, user: dict = Depends(get_current_user)) -> dict:
    target_tenant = payload.tenant_id or user["tenant_id"]
    if not db.get_tenant(target_tenant):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"租户 {target_tenant} 不存在")
    created = db.create_user(payload.username, hash_password(payload.password), role="employee", tenant_id=target_tenant)
    return _public_admin_user(created)


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: AdminUserUpdateRequest, user: dict = Depends(get_current_user)) -> dict:
    target = db.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if target.get("tenant_id", "default") != user.get("tenant_id", "default"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能操作其他租户的用户")
    updated = db.update_user(user_id, enabled=payload.enabled)
    return _public_admin_user(updated)


@router.get("/documents")
async def documents(user: dict = Depends(get_current_user)) -> list[dict]:
    async with AgentRuntime(tenant_id=user.get("tenant_id", "default")) as runtime:
        docs = list_documents(runtime.storage_manager)
    records = {item["id"]: item for item in db.list_document_records(tenant_id=user.get("tenant_id"))}
    for doc in docs:
        doc.update({k: v for k, v in records.get(doc["id"], {}).items() if k not in {"id"}})
    return docs


@router.post("/documents")
async def upload_document(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    _validate_upload(file)
    settings = get_settings()
    upload_dir = Path(settings.storage_dir) / "uploads" / user["tenant_id"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "document.txt").name
    target = upload_dir / f"{uuid4().hex[:8]}_{safe_name}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    async with AgentRuntime(tenant_id=user.get("tenant_id", "default")) as runtime:
        result = await ingest_document(runtime.storage_manager, target)

    db.upsert_document(
        {
            "id": result["doc_id"],
            "source": str(target),
            "uploaded_by": user["id"],
            "status": "ready" if result["ingested"] else "skipped",
            "chunks": result["total_chunks"],
        },
        tenant_id=user.get("tenant_id", "default"),
    )
    return result


@router.delete("/documents/{doc_id}")
async def remove_document(doc_id: str, user: dict = Depends(get_current_user)) -> dict:
    records = db.list_document_records(tenant_id=user.get("tenant_id"))
    if not any(r["id"] == doc_id for r in records):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在或不属于当前租户",
        )
    async with AgentRuntime(tenant_id=user.get("tenant_id", "default")) as runtime:
        result = await delete_document(runtime.storage_manager, doc_id)
    db.delete_document_record(doc_id)
    return result


@router.get("/qa-logs")
def qa_logs(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_qa_logs(limit=200, tenant_id=user.get("tenant_id"))


@router.get("/hard-cases")
def hard_cases(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_hard_cases(limit=200, tenant_id=user.get("tenant_id"))


@router.get("/knowledge-gaps")
def knowledge_gaps(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_knowledge_gaps(limit=50, tenant_id=user.get("tenant_id"))


@router.get("/usage")
async def usage(date: str | None = None, user: dict = Depends(get_current_user)) -> dict:
    return await get_daily_stats(date)


def _public_admin_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "enabled": bool(user.get("enabled", 1)),
        "tenant_id": user.get("tenant_id", "default"),
        "created_at": user.get("created_at", ""),
    }


# ---- Tenant CRUD ----
# 仅 default 租户的用户可管理租户（创建/修改/删除），普通租户只能查看


def _require_system_tenant(user: dict) -> None:
    """仅允许 default 租户的用户执行租户管理操作。"""
    if user.get("tenant_id", "default") != "default":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限操作租户管理")


@router.get("/tenants")
def list_tenants(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_tenants()


@router.post("/tenants")
def create_tenant(payload: TenantCreateRequest, user: dict = Depends(get_current_user)) -> dict:
    _require_system_tenant(user)
    if db.get_tenant(payload.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="租户 ID 已存在")
    return db.create_tenant(payload.id, payload.name, payload.config)


@router.patch("/tenants/{tenant_id}")
def update_tenant(tenant_id: str, payload: TenantUpdateRequest, user: dict = Depends(get_current_user)) -> dict:
    _require_system_tenant(user)
    if not db.get_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="租户不存在")
    updated = db.update_tenant(tenant_id, name=payload.name, config=payload.config)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="租户不存在")
    return updated


@router.delete("/tenants/{tenant_id}")
def delete_tenant(tenant_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_system_tenant(user)
    if tenant_id == "default":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除默认租户")
    if not db.delete_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="租户不存在")
    return {"deleted": tenant_id}
