from app.agent.constants import WORKER_RETRIEVAL
from app.agent.conversation import format_conversation_context
from app.agent.llm import factory as llm_factory
from app.agent.prompts import RETRIEVAL_WORKER_PROMPT, fill_prompt
from app.agent.state import AgentState
from app.agent.storage_manager import StorageManager
from app.agent.tools.search_tool import SearchTool
from app.agent.tools.base import react_loop


def retrieval_worker_node(state: AgentState, storage_manager: StorageManager | None = None) -> dict:
    """检索 Worker：LLM 通过 ReAct 循环自主决定调用 SearchTool 进行知识检索。

    使用 ReAct（而非固定的检索-生成流程）的原因：
    1. LLM 可根据问题性质决定是否检索、检索多少次、何时停止
    2. 不需要检索的问题（如闲聊）直接回复，节省向量搜索开销
    3. Refiner 反馈可影响检索策略（如提示关键词改进）

    storage_manager 通过 partial 注入（在 graph.py 中），运行时注入到 SearchTool。
    每请求创建独立 SearchTool 实例，避免多租户并发下全局单例的 storage_manager 被覆盖。
    """
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进检索。" if feedback else ""

    prompt = fill_prompt(RETRIEVAL_WORKER_PROMPT,
        refinement_context=refinement_context,
        user_message=user_message,
        conversation_context=format_conversation_context(messages),
    )

    # 每请求创建独立 SearchTool 实例，避免全局单例的竞态问题
    search_tool = SearchTool(storage_manager=storage_manager)
    tools = search_tool.get_lc_tools()

    content = react_loop(llm, prompt, tools)

    # 低置信度检测启发式：知识库中有文档但搜索结果显示"未找到相关信息"
    # 这是一个简化实现——精确判断需要 LLM 输出结构化置信度评分，
    # 但考虑到成本和延迟，使用关键词匹配已经足够触发反思流程
    has_docs = bool(storage_manager and storage_manager.has_documents)
    low_confidence = has_docs and ("未找到" in content and "相关信息" in content)

    return {
        "worker_results": [
            {
                "worker": WORKER_RETRIEVAL,
                "content": content,
                "error": None,
                "metadata": {
                    "has_documents": has_docs,
                    "refinement_count": state.get("refinement_count", 0),
                    "low_confidence": low_confidence,  # 供 route_after_summary 做路由决策
                },
            }
        ]
    }
