from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def format_conversation_context(messages: list[BaseMessage], limit: int = 8) -> str:
    """Format chat messages for prompts, compressing older turns when over limit."""
    if len(messages) <= 1:
        return "（暂无历史对话）"

    if len(messages) > limit:
        older = messages[:-limit]
        recent = messages[-limit:]
        summary = _compress(older)
        formatted = _format_messages(recent)
        return f"{summary}\n\n{formatted}" if summary else formatted

    return _format_messages(messages[-limit:])


def _compress(messages: list[BaseMessage]) -> str:
    """压缩较早对话为一句话摘要。"""
    if not messages:
        return ""
    count = len(messages)

    try:
        text = _format_messages(messages, max_length=2000)
        settings = get_settings()
        if settings.llm_api_key:
            from langchain.chat_models import init_chat_model

            llm = init_chat_model(
                settings.llm_model,
                model_provider="openai",
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                temperature=0,
            )
            prompt = (
                "用一句话概括以下对话的关键话题和结论。只输出概括，不要多余内容。\n\n"
                f"对话：\n{text}"
            )
            resp = llm.invoke(prompt)
            summary = resp.content if hasattr(resp, "content") else str(resp)
            return f"【历史对话概要】{summary.strip()}"
    except Exception:
        logger.warning("LLM conversation compression failed", exc_info=True)

    return f"【省略了前面 {count} 轮对话】"


def _format_messages(messages: list[BaseMessage], max_length: int = 0) -> str:
    """格式化消息列表为纯文本。"""
    lines: list[str] = []
    for message in messages:
        content = str(message.content).strip()
        if not content:
            continue
        if max_length and len(content) > max_length:
            content = content[:max_length] + "..."

        if isinstance(message, HumanMessage):
            role = "用户"
        elif isinstance(message, AIMessage):
            role = "助手"
        else:
            role = message.type or "消息"
        lines.append(f"{role}: {content}")

    return "\n".join(lines) if lines else "（暂无历史对话）"
