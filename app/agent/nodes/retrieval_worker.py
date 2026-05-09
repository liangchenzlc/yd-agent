from app.agent.constants import WORKER_RETRIEVAL
from app.agent.llm import factory as llm_factory
from app.agent.prompts import RETRIEVAL_WORKER_PROMPT
from app.agent.state import AgentState
from app.agent.storage_manager import StorageManager
from app.agent.tools import ToolRegistry


def retrieval_worker_node(state: AgentState, storage_manager: StorageManager | None = None) -> dict:
    """检索 Worker：使用 SearchTool 执行 GraphRAG 检索。"""
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进检索。" if feedback else ""

    # 通过 SearchTool 执行检索
    search_tool = ToolRegistry.get("search")
    search_result = search_tool.run(
        query=user_message,
        storage_manager=storage_manager,
    )

    llm = llm_factory.create_llm()
    prompt = (
        RETRIEVAL_WORKER_PROMPT.replace("{refinement_context}", refinement_context)
        .replace("{graphrag_context}", search_result["context"])
        .replace("{user_message}", user_message)
    )
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)

    return {
        "worker_results": [
            {
                "worker": WORKER_RETRIEVAL,
                "content": content,
                "error": None,
                "metadata": {
                    "has_documents": search_result.get("has_documents", False),
                    "entity_count": len(search_result.get("entities", [])),
                    "relation_count": len(search_result.get("relations", [])),
                },
            }
        ]
    }
