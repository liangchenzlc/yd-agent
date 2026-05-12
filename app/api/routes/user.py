from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.services.documents import list_documents
from app.runtime import AgentRuntime
from app.web.auth import create_token, get_current_user, verify_password
from app.web.chat_service import run_chat_turn
from app.web.db import db
from app.web.schemas import AuthRequest, AuthResponse, ChatRequest, ChatResponse, FeedbackRequest

router = APIRouter(prefix="/api", tags=["user"])


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: AuthRequest, response: Response) -> dict:
    user = db.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.get("enabled", 1):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    token = create_token(user)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=24 * 60 * 60,
    )
    return {"token": token, "user": _public_user(user)}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return _public_user(user)


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: dict = Depends(get_current_user)) -> dict:
    return await run_chat_turn(user, payload.message, payload.session_id)


@router.get("/sessions")
def sessions(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_sessions(user["id"])


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: str, user: dict = Depends(get_current_user)) -> list[dict]:
    if not db.get_session(user["id"], session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return db.list_messages(session_id, user["id"], limit=100)


@router.get("/documents")
async def documents(user: dict = Depends(get_current_user)) -> list[dict]:
    async with AgentRuntime() as runtime:
        docs = list_documents(runtime.storage_manager)
    records = {item["id"]: item for item in db.list_document_records()}
    for doc in docs:
        doc.update({k: v for k, v in records.get(doc["id"], {}).items() if k not in {"id"}})
    return docs


@router.post("/feedback")
def feedback(payload: FeedbackRequest, user: dict = Depends(get_current_user)) -> dict:
    return db.add_feedback(payload.qa_log_id, user["id"], payload.rating, payload.comment)


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"], "role": user["role"]}
