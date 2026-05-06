from app.agent.state import AgentState
from app.agent.prompts import RETRIEVAL_WORKER_PROMPT
from app.agent.llm import factory as llm_factory
from app.agent.constants import WORKER_RETRIEVAL


def retrieval_worker_node(state: AgentState) -> dict:
    """检索 Worker：执行知识检索（一期为关键词搜索占位）。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    if feedback:
        refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进检索。"
    else:
        refinement_context = ""

    prompt = RETRIEVAL_WORKER_PROMPT.replace("{refinement_context}", refinement_context).replace("{user_message}", user_message)
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)

    return {
        "worker_results": [
            {
                "worker": WORKER_RETRIEVAL,
                "content": content,
                "error": None,
                "metadata": {},
            }
        ]
    }
