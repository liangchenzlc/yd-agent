import re
from datetime import datetime, timezone

from app.agent.state import AgentState
from app.agent.prompts import DOCS_WORKER_PROMPT
from app.agent.llm import factory as llm_factory
from app.agent.constants import WORKER_DOCS
from app.agent.tools import ToolRegistry


def _extract_title(content: str) -> str:
    """从 Markdown 内容中提取标题用于文件名。"""
    m = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    if m:
        return m.group(1).strip().lower().replace(" ", "_").replace("/", "_")[:40]
    return f"doc_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def docs_worker_node(state: AgentState) -> dict:
    """文档 Worker：LLM 生成文档内容 → DocTool 写入文件。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进文档。" if feedback else ""

    prompt = DOCS_WORKER_PROMPT.replace("{refinement_context}", refinement_context).replace("{user_message}", user_message)
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)

    file_name = f"{_extract_title(content)}.md"
    doc_tool = ToolRegistry.get("doc")
    write_result = doc_tool.run(file_path=file_name, content=content)

    return {
        "worker_results": [
            {
                "worker": WORKER_DOCS,
                "content": f"文档已生成：{write_result.get('file_path', file_name)}",
                "error": None if write_result.get("success") else write_result.get("error"),
                "metadata": {
                    "file_path": write_result.get("file_path", ""),
                    "file_name": file_name,
                    "size": write_result.get("size", len(content)),
                },
            }
        ]
    }
