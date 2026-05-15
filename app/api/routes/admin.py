from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.agent.stats.usage_tracker import get_daily_stats
from app.config.settings import get_settings
from app.runtime import AgentRuntime
from app.services.documents import delete_document, ingest_document, list_documents
from app.web.auth import hash_password, require_admin
from app.web.db import db
from app.web.schemas import AdminUserCreateRequest, AdminUserUpdateRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/json",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _validate_upload(file: UploadFile) -> None:
    """验证上传文件：Content-Type、大小、magic bytes。"""
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
    """常见文档格式的 magic bytes 检查。"""
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
def users(user: dict = Depends(require_admin)) -> list[dict]:
    return db.list_users()


@router.post("/users")
def create_user(payload: AdminUserCreateRequest, user: dict = Depends(require_admin)) -> dict:
    created = db.create_user(payload.username, hash_password(payload.password), role=payload.role, tenant_id=payload.tenant_id)
    return _public_admin_user(created)


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: AdminUserUpdateRequest, user: dict = Depends(require_admin)) -> dict:
    updated = db.update_user(user_id, role=payload.role, enabled=payload.enabled)
    if updated is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _public_admin_user(updated)


@router.get("/documents")
async def documents(user: dict = Depends(require_admin)) -> list[dict]:
    async with AgentRuntime(tenant_id=user.get("tenant_id", "default")) as runtime:
        docs = list_documents(runtime.storage_manager)
    records = {item["id"]: item for item in db.list_document_records()}
    for doc in docs:
        doc.update({k: v for k, v in records.get(doc["id"], {}).items() if k not in {"id"}})
    return docs


@router.post("/documents")
async def upload_document(file: UploadFile = File(...), user: dict = Depends(require_admin)) -> dict:
    _validate_upload(file)
    settings = get_settings()
    upload_dir = Path(settings.storage_dir) / "uploads"
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
            "entities": result["total_entities"],
            "relationships": result["total_relationships"],
        }
    )
    return result


@router.delete("/documents/{doc_id}")
async def remove_document(doc_id: str, user: dict = Depends(require_admin)) -> dict:
    async with AgentRuntime(tenant_id=user.get("tenant_id", "default")) as runtime:
        result = await delete_document(runtime.storage_manager, doc_id)
    db.delete_document_record(doc_id)
    return result


@router.get("/qa-logs")
def qa_logs(user: dict = Depends(require_admin)) -> list[dict]:
    return db.list_qa_logs(limit=200)


@router.get("/hard-cases")
def hard_cases(user: dict = Depends(require_admin)) -> list[dict]:
    return db.list_hard_cases(limit=200)


@router.get("/knowledge-gaps")
def knowledge_gaps(user: dict = Depends(require_admin)) -> list[dict]:
    return db.list_knowledge_gaps(limit=50)


@router.get("/usage")
async def usage(date: str | None = None, user: dict = Depends(require_admin)) -> dict:
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
