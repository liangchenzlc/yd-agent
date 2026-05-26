from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from app.agent.state import AgentState
from app.runtime import AgentRuntime
from app.services.documents import list_documents
from app.web.auth import create_token, get_current_user, verify_password
from app.web.chat_service import run_chat_turn
from app.web.db import db
from app.web.schemas import AuthRequest, AuthResponse, ChatRequest, ChatResponse, FeedbackRequest

router = APIRouter(prefix="/api", tags=["user"])


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: AuthRequest, response: Response) -> dict:
    """管理后台登录：super_admin 和 admin 均可登录。"""
    user = db.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user["role"] not in ("super_admin", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问管理后台")
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


@router.post("/user/login", response_model=AuthResponse)
def user_login(payload: AuthRequest, response: Response) -> dict:
    """用户前端登录：仅 user 角色可登录。"""
    user = db.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user["role"] != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该账号无权登录用户端")
    if not user.get("enabled", 1):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    token = create_token(user)
    return {"token": token, "user": {"id": user["id"], "username": user["username"]}}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return _public_user(user)


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: dict = Depends(get_current_user)) -> dict:
    return await run_chat_turn(user, payload.message, payload.session_id)


@router.get("/chat/stream")
async def chat_stream(
    message: str = Query(min_length=1),
    session_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """SSE 流式聊天：实时推送 Agent 执行进度。"""
    resolved_session_id = session_id or uuid4().hex[:12]
    return StreamingResponse(
        _stream_agent(user, message, resolved_session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_agent(user: dict, message: str, session_id: str) -> str:
    from langchain_core.messages import HumanMessage

    from app.agent.state import AgentState

    yield f"event: meta\ndata: {json.dumps({'session_id': session_id})}\n\n"

    state = AgentState(
        messages=[HumanMessage(content=message)],
        worker_assignments=[],
        dispatch_reasoning="",
        worker_results=[],
        refinement_count=0,
        refinement_needed=False,
        refinement_feedback="",
        refinement_targets=[],
        final_answer="",
        user_id=str(user["id"]),
        session_id=session_id,
        user_profile={},
        relevant_memories=[],
        session_history=[],
    )

    tenant_id = user.get("tenant_id") or "default"

    async with AgentRuntime(tenant_id=tenant_id) as runtime:
        final_answer = ""
        worker_assignments: list[str] = []
        worker_results_list: list[dict] = []
        dispatch_reasoning = ""

        async for chunk in runtime.graph.astream(state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                if node_name == "supervisor":
                    dispatch_reasoning = node_output.get("dispatch_reasoning", "")
                    worker_assignments = node_output.get("worker_assignments", [])
                    event = {
                        "type": "supervisor",
                        "reasoning": dispatch_reasoning,
                        "workers": worker_assignments,
                    }
                elif node_name == "summary_worker":
                    final_answer = node_output.get("final_answer", "")
                    worker_results_list = node_output.get("worker_results", [])
                    event = {"type": "summary", "content": final_answer}
                elif node_name == "refiner":
                    needed = node_output.get("refinement_needed", False)
                    event = {"type": "refiner", "passed": not needed, "feedback": node_output.get("refinement_feedback", "")}
                elif node_name in ("load_memory", "save_memory"):
                    continue
                else:
                    event = {"type": "worker", "worker": node_name}

                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    from app.web.db import db

    db.ensure_session(user["id"], session_id, message[:40], tenant_id=tenant_id)
    db.add_message(session_id, user["id"], "user", message, tenant_id=tenant_id)
    qa_log = db.add_qa_log(
        session_id=session_id,
        user_id=user["id"],
        question=message,
        answer=final_answer,
        workers=worker_assignments,
        dispatch_reasoning=dispatch_reasoning,
        worker_results=worker_results_list,
        confidence=None,
        tenant_id=tenant_id,
    )
    db.add_message(session_id, user["id"], "assistant", final_answer, tenant_id=tenant_id, qa_log_id=qa_log["id"])

    yield f"event: done\ndata: {json.dumps({'type': 'done', 'session_id': session_id, 'qa_log_id': qa_log['id']})}\n\n"


@router.get("/sessions")
def sessions(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_sessions(user["id"])


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: str, user: dict = Depends(get_current_user)) -> list[dict]:
    if not db.get_session(user["id"], session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return db.list_messages(session_id, user["id"], limit=100)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    if not db.delete_session(user["id"], session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return {"deleted": session_id}


@router.get("/documents")
async def documents(user: dict = Depends(get_current_user)) -> list[dict]:
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有关联租户")
    async with AgentRuntime(tenant_id=tenant_id) as runtime:
        docs = list_documents(runtime.storage_manager)
    records = {item["id"]: item for item in db.list_document_records(tenant_id=tenant_id)}
    for doc in docs:
        doc.update({k: v for k, v in records.get(doc["id"], {}).items() if k not in {"id"}})
        doc.setdefault("entities", 0)
        doc.setdefault("relationships", 0)
    return docs


@router.post("/feedback")
def feedback(payload: FeedbackRequest, user: dict = Depends(get_current_user)) -> dict:
    return db.add_feedback(payload.qa_log_id, user["id"], payload.rating, payload.comment,
                           tenant_id=user.get("tenant_id", "default"))


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"], "role": user["role"]}
