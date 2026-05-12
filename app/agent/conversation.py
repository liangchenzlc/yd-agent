from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def format_conversation_context(messages: list[BaseMessage], limit: int = 8) -> str:
    """Format recent chat messages for prompts."""
    if len(messages) <= 1:
        return "（暂无历史对话）"

    recent = messages[-limit:]
    lines: list[str] = []
    for message in recent:
        content = str(message.content).strip()
        if not content:
            continue
        if isinstance(message, HumanMessage):
            role = "用户"
        elif isinstance(message, AIMessage):
            role = "助手"
        else:
            role = message.type or "消息"
        lines.append(f"{role}: {content[:1200]}")

    return "\n".join(lines) if lines else "（暂无历史对话）"
