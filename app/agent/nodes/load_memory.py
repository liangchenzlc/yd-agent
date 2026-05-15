from app.agent.llm import factory as llm_factory
from app.agent.memory.memory_manager import MemoryManager
from app.agent.memory.retriever import format_memory_context, format_profile_context
from app.agent.state import AgentState


async def load_memory_node(
    state: AgentState,
    memory_manager: MemoryManager | None = None,
) -> dict:
    """加载用户画像和相关记忆，注入 AgentState。"""
    if memory_manager is None:
        return {"user_profile": {}, "relevant_memories": [], "session_history": []}

    user_id = state.get("user_id", "default")
    messages = state.get("messages", [])
    query = messages[-1].content if messages else ""

    # 加载画像
    profile = (await memory_manager.get_user_profile(user_id)) or {}

    # 检索相关记忆
    embeddings_api = llm_factory.create_embeddings()
    relevant = (
        await memory_manager.get_relevant_memories(user_id, query, embeddings_api)
        if query
        else []
    )

    # 会话历史
    session_history = (await memory_manager.get_session_history(user_id)) or []

    return {
        "user_profile": profile,
        "relevant_memories": relevant,
        "session_history": session_history,
    }
