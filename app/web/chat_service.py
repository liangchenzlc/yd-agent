from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.state import AgentState
from app.agent.stats.usage_tracker import estimate_tokens, track_api_call, track_llm_tokens
from app.agent.storage.redis_cache import redis_cache
from app.runtime import AgentRuntime
from app.web.db import db

SESSION_TTL = 3600  # 1 hour cache for session data


def _state_from_messages(messages: list[BaseMessage], user_id: str, session_id: str,
                         tenant_id: str = "default") -> AgentState:
    return AgentState(
        messages=messages,
        worker_assignments=[],
        dispatch_reasoning="",
        worker_results=[],
        refinement_count=0,
        refinement_needed=False,
        refinement_feedback="",
        refinement_targets=[],
        final_answer="",
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        user_profile={},
        relevant_memories=[],
        session_history=[],
    )


def _messages_from_history(history: list[dict], new_message: str) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history:
        if item["role"] == "user":
            messages.append(HumanMessage(content=item["content"]))
        elif item["role"] == "assistant":
            messages.append(AIMessage(content=item["content"]))
    messages.append(HumanMessage(content=new_message))
    return messages


async def _get_cached_history(session_id: str, user_id: int, limit: int = 20) -> list[dict] | None:
    cache_key = f"session:{session_id}:history"
    return await redis_cache.get(cache_key)


async def _set_cached_history(session_id: str, history: list[dict]) -> None:
    cache_key = f"session:{session_id}:history"
    await redis_cache.set(cache_key, history, ttl=SESSION_TTL)


async def run_chat_turn(user: dict, message: str, session_id: str | None = None) -> dict:
    resolved_session_id = session_id or uuid4().hex[:12]
    title = message[:40] or "新会话"
    tenant_id = user.get("tenant_id", "default")
    db.ensure_session(user["id"], resolved_session_id, title, tenant_id=tenant_id)

    # 优先从 Redis 缓存加载历史，未命中则从 SQLite 加载
    history = await _get_cached_history(resolved_session_id, user["id"])
    if history is None:
        history = db.list_messages(resolved_session_id, user["id"], limit=20)
        await _set_cached_history(resolved_session_id, history)

    messages = _messages_from_history(history, message)

    async with AgentRuntime(tenant_id=tenant_id) as runtime:
        state = _state_from_messages(messages, str(user["id"]), resolved_session_id, tenant_id=tenant_id)
        result = await runtime.graph.ainvoke(state)

    answer = result.get("final_answer", "")
    workers = result.get("worker_assignments", [])
    worker_results = result.get("worker_results", [])
    dispatch_reasoning = result.get("dispatch_reasoning", "")

    # 记录用量
    await track_api_call(user["id"], tenant_id, "/api/chat")
    input_tokens = estimate_tokens(message)
    output_tokens = estimate_tokens(answer)
    await track_llm_tokens(user["id"], "chat", input_tokens, output_tokens, tenant_id=tenant_id)

    # 持久化到 SQLite（先创建 qa_log 拿到 id，再保存 assistant 消息）
    db.add_message(resolved_session_id, user["id"], "user", message, tenant_id=tenant_id)
    qa_log = db.add_qa_log(
        session_id=resolved_session_id,
        user_id=user["id"],
        question=message,
        answer=answer,
        workers=workers,
        dispatch_reasoning=dispatch_reasoning,
        worker_results=worker_results,
        confidence=_infer_confidence(worker_results),
        tenant_id=tenant_id,
    )
    db.add_message(resolved_session_id, user["id"], "assistant", answer, tenant_id=tenant_id, qa_log_id=qa_log["id"])

    # 刷新 Redis 缓存
    updated_history = db.list_messages(resolved_session_id, user["id"], limit=20)
    await _set_cached_history(resolved_session_id, updated_history)

    return {
        "answer": answer,
        "session_id": resolved_session_id,
        "qa_log_id": qa_log["id"],
        "workers_used": workers,
        "dispatch_reasoning": dispatch_reasoning,
        "worker_results": worker_results,
    }


def _infer_confidence(worker_results: list[dict]) -> float | None:
    text = "\n".join(str(item.get("content", "")) for item in worker_results)
    if not text:
        return None
    if "未找到" in text or "无法检索" in text:
        return 0.1
    if "low_confidence" in text:
        return 0.3
    return 0.8
