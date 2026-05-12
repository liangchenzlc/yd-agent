from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.state import AgentState
from app.runtime import AgentRuntime
from app.web.db import db


def _state_from_messages(messages: list[BaseMessage], user_id: str, session_id: str) -> AgentState:
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


async def run_chat_turn(user: dict, message: str, session_id: str | None = None) -> dict:
    resolved_session_id = session_id or uuid4().hex[:12]
    title = message[:40] or "新会话"
    db.ensure_session(user["id"], resolved_session_id, title)
    history = db.list_messages(resolved_session_id, user["id"], limit=20)
    messages = _messages_from_history(history, message)

    async with AgentRuntime() as runtime:
        state = _state_from_messages(messages, str(user["id"]), resolved_session_id)
        result = await runtime.graph.ainvoke(state)

    answer = result.get("final_answer", "")
    workers = result.get("worker_assignments", [])
    worker_results = result.get("worker_results", [])
    dispatch_reasoning = result.get("dispatch_reasoning", "")

    db.add_message(resolved_session_id, user["id"], "user", message)
    db.add_message(resolved_session_id, user["id"], "assistant", answer)
    qa_log = db.add_qa_log(
        session_id=resolved_session_id,
        user_id=user["id"],
        question=message,
        answer=answer,
        workers=workers,
        dispatch_reasoning=dispatch_reasoning,
        worker_results=worker_results,
        confidence=_infer_confidence(worker_results),
    )

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
