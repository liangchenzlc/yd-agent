from app.agent.llm import factory as llm_factory
from app.agent.memory.extractor import extract_memories_from_conversation
from app.agent.memory.memory_manager import MemoryManager
from app.agent.state import AgentState
from app.config.settings import get_settings


async def save_memory_node(
    state: AgentState,
    memory_manager: MemoryManager | None = None,
) -> dict:
    """从本次对话中提取记忆并存储。"""
    if memory_manager is None:
        return {"memories_updated": False}

    settings = get_settings()
    if not settings.memory_extraction_enabled:
        return {"memories_updated": False}

    user_id = state.get("user_id", "default")
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""
    final_answer = state.get("final_answer", "")

    # 提取记忆
    memories = extract_memories_from_conversation(user_message, final_answer)

    # 过滤低重要性记忆
    threshold = settings.memory_importance_threshold
    significant = [m for m in memories if m.get("importance", 0) >= threshold or m.get("type") == "fact"]

    # 存储记忆
    if significant:
        embeddings_api = llm_factory.create_embeddings()
        session_id = state.get("session_id", state.get("user_id", "unknown"))
        await memory_manager.store_session_memory(
            user_id=user_id,
            session_id=session_id,
            memories=significant,
            embeddings_api=embeddings_api,
            importance_threshold=settings.memory_importance_threshold,
        )

    # 无论是否有记忆被提取，都更新用户画像（交互计数和最近历史）
    await memory_manager.update_user_profile(
        user_id=user_id,
        message=user_message,
        answer=final_answer,
    )

    return {"memories_updated": bool(significant)}
