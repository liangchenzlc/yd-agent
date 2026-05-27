from app.agent.constants import WORKER_DOCS
from app.agent.conversation import format_conversation_context
from app.agent.llm import factory as llm_factory
from app.agent.prompts import DOCS_WORKER_PROMPT, fill_prompt
from app.agent.state import AgentState
from app.agent.tools import FileTool, ToolRegistry, react_loop


def docs_worker_node(state: AgentState) -> dict:
    """文档 Worker：LLM 通过 ReAct 循环自主决定调用 FileTool 进行文件操作。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进文档。" if feedback else ""

    # 创建独立 FileTool 实例，避免并行 Worker 共享单例导致产物交叉
    file_tool = FileTool(worker="docs")
    tools = file_tool.get_lc_tools()
    tools_description = "\n".join(f"- {t.name}: {t.description}" for t in tools)

    prompt = fill_prompt(DOCS_WORKER_PROMPT,
        tools_description=tools_description,
        refinement_context=refinement_context,
        user_message=user_message,
        conversation_context=format_conversation_context(messages),
    )

    content = react_loop(llm, prompt, tools)

    # 提取工具生成的产物
    artifacts = file_tool.pop_artifacts()

    return {
        "worker_results": [
            {
                "worker": WORKER_DOCS,
                "content": content,
                "error": None,
                "metadata": {"refinement_count": state.get("refinement_count", 0)},
                "artifacts": artifacts,
            }
        ]
    }
