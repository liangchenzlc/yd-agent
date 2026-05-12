from app.agent.constants import WORKER_CODE
from app.agent.conversation import format_conversation_context
from app.agent.llm import factory as llm_factory
from app.agent.prompts import CODE_WORKER_PROMPT
from app.agent.state import AgentState
from app.agent.tools import DockerSandBoxTool, ToolRegistry, react_loop


def code_worker_node(state: AgentState) -> dict:
    """代码 Worker：LLM 通过 ReAct 循环自主决定调用 DockerSandBoxTool。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    # 注入纠错反馈
    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮错误\n之前的代码执行失败，反馈如下：\n{feedback}\n请修复代码。" if feedback else ""

    prompt = (
        CODE_WORKER_PROMPT.replace("{refinement_context}", refinement_context)
        .replace("{user_message}", user_message)
        .replace("{conversation_context}", format_conversation_context(messages))
    )

    # 绑定 DockerSandBoxTool 工具，LLM 自主决定是否调用
    docker_tool = ToolRegistry.get("docker_sandbox")
    tools = docker_tool.get_lc_tools()

    content = react_loop(llm, prompt, tools)

    return {
        "worker_results": [
            {
                "worker": WORKER_CODE,
                "content": content,
                "error": None,
                "metadata": {"refinement_count": state.get("refinement_count", 0)},
            }
        ]
    }
