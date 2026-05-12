from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile

from app.config.settings import get_settings
from app.runtime import AgentRuntime
from app.services.documents import delete_document, ingest_document, list_documents
from app.web.auth import hash_password, require_admin
from app.web.db import db
from app.web.schemas import AdminUserCreateRequest, AdminUserUpdateRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def users(user: dict = Depends(require_admin)) -> list[dict]:
    return db.list_users()


@router.post("/users")
def create_user(payload: AdminUserCreateRequest, user: dict = Depends(require_admin)) -> dict:
    created = db.create_user(payload.username, hash_password(payload.password), role=payload.role)
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
    async with AgentRuntime() as runtime:
        docs = list_documents(runtime.storage_manager)
    records = {item["id"]: item for item in db.list_document_records()}
    for doc in docs:
        doc.update({k: v for k, v in records.get(doc["id"], {}).items() if k not in {"id"}})
    return docs


@router.post("/documents")
async def upload_document(file: UploadFile = File(...), user: dict = Depends(require_admin)) -> dict:
    settings = get_settings()
    upload_dir = Path(settings.storage_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "document.txt").name
    target = upload_dir / f"{uuid4().hex[:8]}_{safe_name}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    async with AgentRuntime() as runtime:
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
    async with AgentRuntime() as runtime:
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


def _public_admin_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "enabled": bool(user.get("enabled", 1)),
        "created_at": user.get("created_at", ""),
    }
