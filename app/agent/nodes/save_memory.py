from app.agent.llm import factory as llm_factory
from app.agent.memory.extractor import extract_memories_from_conversation
from app.agent.memory.memory_manager import MemoryManager
from app.agent.state import AgentState
from app.config.settings import get_settings


def save_memory_node(
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

    # LangGraph 节点接口限定为同步函数，但 MemoryManager 方法是异步的。
    # 此处通过 run_until_complete 桥接异步调用。
    # 注意：若将来 LangGraph 支持 async 节点，应移除该 workaround。
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # 存储记忆
    if significant:
        embeddings_api = llm_factory.create_embeddings()
        session_id = state.get("session_id", state.get("user_id", "unknown"))
        loop.run_until_complete(
            memory_manager.store_session_memory(
                user_id=user_id,
                session_id=session_id,
                memories=significant,
                embeddings_api=embeddings_api,
                importance_threshold=settings.memory_importance_threshold,
            )
        )

    # 无论是否有记忆被提取，都更新用户画像（交互计数和最近历史）
    loop.run_until_complete(
        memory_manager.update_user_profile(
            user_id=user_id,
            message=user_message,
            answer=final_answer,
        )
    )

    return {"memories_updated": bool(significant)}
