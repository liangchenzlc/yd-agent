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

    prompt = fill_prompt(DOCS_WORKER_PROMPT,
        refinement_context=refinement_context,
        user_message=user_message,
        conversation_context=format_conversation_context(messages),
    )

    # 绑定 FileTool 工具，LLM 自主决定调用 write_file / read_file / list_files
    file_tool = ToolRegistry.get("file")
    tools = file_tool.get_lc_tools()

    content = react_loop(llm, prompt, tools)

    return {
        "worker_results": [
            {
                "worker": WORKER_DOCS,
                "content": content,
                "error": None,
                "metadata": {"refinement_count": state.get("refinement_count", 0)},
            }
        ]
    }
