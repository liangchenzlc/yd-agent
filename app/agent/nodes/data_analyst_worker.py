import logging

from app.agent.constants import WORKER_DATA_ANALYST
from app.agent.conversation import format_conversation_context
from app.agent.llm import factory as llm_factory
from app.agent.prompts import DATA_ANALYST_PROMPT, fill_prompt
from app.agent.state import AgentState
from app.agent.tools import ToolRegistry, react_loop
from app.agent.tools.database_tool import DatabaseTool
from app.agent.tools.report_tool import ReportTool
from app.web.db import db

logger = logging.getLogger(__name__)

MAX_PREFETCH_TABLES = 5


def _parse_table_names(tables_result: str) -> list[str]:
    """从 list_tables 返回文本中解析表名列表。"""
    tables = []
    for line in tables_result.splitlines():
        line = line.strip()
        if line.startswith("- ") or line.startswith("  - "):
            name = line.lstrip("- ").strip()
            if name:
                tables.append(name)
    return tables


def _prefetch_db_context(db_tool) -> str:
    """预取数据库表结构和样本数据。"""
    tables_result = db_tool.list_tables()
    if tables_result.startswith("错误"):
        return "## 数据库概览\n" + tables_result

    ctx_parts = ["## 数据库概览", tables_result, ""]
    tables = _parse_table_names(tables_result)

    for table in tables[:MAX_PREFETCH_TABLES]:
        schema = db_tool.get_table_schema(table)
        if "不存在" in schema:
            continue
        ctx_parts.append(f"### {table} 表结构")
        ctx_parts.append(schema)
        ctx_parts.append("")
        sample = db_tool.execute_sql(f"SELECT * FROM {table} LIMIT 20")
        if not sample.startswith("错误"):
            ctx_parts.append(f"### {table} 样本数据（前 20 行）")
            ctx_parts.append(sample)
            ctx_parts.append("")

    return "\n".join(ctx_parts)


def data_analyst_worker_node(state: AgentState) -> dict:
    """数据分析 Worker：LLM 通过 ReAct 循环查询数据库并生成图表。

    从 AgentState 获取 tenant_id，查找该租户在管理后台配置的数据源，
    使用租户专属的数据库连接执行 text-to-SQL 和图表生成。
    """
    try:
        tenant_id = state.get("tenant_id", "")
        user_message = (state.get("messages", []) or [None])[-1]
        user_message = user_message.content if user_message else ""

        # 查找租户数据源配置
        ds = db.get_data_source(tenant_id) if tenant_id else None
        if not ds:
            return {
                "worker_results": [
                    {
                        "worker": WORKER_DATA_ANALYST,
                        "content": "当前租户未配置数据源。请联系管理员在管理后台【数据源配置】中添加数据库连接，然后重试。",
                        "error": None,
                        "metadata": {"refinement_count": state.get("refinement_count", 0)},
                        "artifacts": [],
                    }
                ]
            }

        # 使用租户数据源创建独立实例，避免并行 Worker 共享单例导致产物交叉
        db_tool = DatabaseTool(db_config={
            "type": ds["db_type"],
            "host": ds["db_host"],
            "port": ds["db_port"],
            "user": ds["db_user"],
            "password": ds["db_password"],
            "database": ds["db_database"],
        })
        report_tool = ReportTool()

        llm = llm_factory.create_llm()
        feedback = state.get("refinement_feedback", "")
        refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进数据分析。" if feedback else ""

        tools = db_tool.get_lc_tools() + report_tool.get_lc_tools()
        tools_description = "\n".join(f"- {t.name}: {t.description}" for t in tools)

        db_context = _prefetch_db_context(db_tool)

        prompt = fill_prompt(DATA_ANALYST_PROMPT,
            tools_description=tools_description,
            refinement_context=refinement_context,
            user_message=user_message,
            conversation_context=format_conversation_context(state.get("messages", [])),
            db_context=db_context,
        )

        content = react_loop(llm, prompt, tools)

        # 提取工具生成的产物
        artifacts = report_tool.pop_artifacts()

        return {
            "worker_results": [
                {
                    "worker": WORKER_DATA_ANALYST,
                    "content": content,
                    "error": None,
                    "metadata": {"refinement_count": state.get("refinement_count", 0)},
                    "artifacts": artifacts,
                }
            ]
        }
    except Exception as e:
        logger.exception("data_analyst_worker_node 执行异常")
        return {
            "worker_results": [
                {
                    "worker": WORKER_DATA_ANALYST,
                    "content": "",
                    "error": str(e),
                    "metadata": {"refinement_count": state.get("refinement_count", 0)},
                    "artifacts": [],
                }
            ]
        }
