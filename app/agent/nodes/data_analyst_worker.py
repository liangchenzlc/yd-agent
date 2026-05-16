from app.agent.constants import WORKER_DATA_ANALYST
from app.agent.conversation import format_conversation_context
from app.agent.llm import factory as llm_factory
from app.agent.prompts import DATA_ANALYST_PROMPT, fill_prompt
from app.agent.state import AgentState
from app.agent.tools import ToolRegistry, react_loop


def data_analyst_worker_node(state: AgentState) -> dict:
    """数据分析 Worker：LLM 通过 ReAct 循环查询数据库并生成图表。

    合并 DatabaseTool（SQL 查询）和 ReportTool（数据可视化/报表生成）两个工具集，
    让 LLM 可以在一次 ReAct 循环内完成"查数据 → 画图表 → 解读结果"的完整流程。
    两个工具集共存在同一个 prompt 中，LLM 自主决定调用顺序和次数。
    """
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进数据分析。" if feedback else ""

    # 合并 DatabaseTool 和 ReportTool 的所有工具
    db_tool = ToolRegistry.get("database")
    report_tool = ToolRegistry.get("report")
    tools = db_tool.get_lc_tools() + report_tool.get_lc_tools()
    tools_description = "\n".join(f"- {t.name}: {t.description}" for t in tools)

    prompt = fill_prompt(DATA_ANALYST_PROMPT,
        tools_description=tools_description,
        refinement_context=refinement_context,
        user_message=user_message,
        conversation_context=format_conversation_context(messages),
    )

    content = react_loop(llm, prompt, tools)

    return {
        "worker_results": [
            {
                "worker": WORKER_DATA_ANALYST,
                "content": content,
                "error": None,
                "metadata": {"refinement_count": state.get("refinement_count", 0)},
            }
        ]
    }
