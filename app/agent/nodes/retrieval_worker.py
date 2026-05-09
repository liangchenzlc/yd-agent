from app.agent.constants import WORKER_RETRIEVAL
from app.agent.llm import factory as llm_factory
from app.agent.prompts import RETRIEVAL_WORKER_PROMPT
from app.agent.state import AgentState
from app.agent.storage_manager import StorageManager
from app.agent.tools import ToolRegistry, react_loop


def retrieval_worker_node(state: AgentState, storage_manager: StorageManager | None = None) -> dict:
    """检索 Worker：LLM 通过 ReAct 循环自主决定调用 SearchTool 进行知识检索。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进检索。" if feedback else ""

    prompt = (
        RETRIEVAL_WORKER_PROMPT.replace("{refinement_context}", refinement_context)
        .replace("{user_message}", user_message)
    )

    # 向已注册的 SearchTool 注入 storage_manager，LLM 自主决定是否检索
    search_tool = ToolRegistry.get("search")
    search_tool.set_storage_manager(storage_manager)
    tools = search_tool.get_lc_tools()

    content = react_loop(llm, prompt, tools)

    return {
        "worker_results": [
            {
                "worker": WORKER_RETRIEVAL,
                "content": content,
                "error": None,
                "metadata": {
                    "has_documents": bool(storage_manager and storage_manager.has_documents),
                },
            }
        ]
    }
