import re

from app.agent.state import AgentState
from app.agent.prompts import CODE_WORKER_PROMPT
from app.agent.llm import factory as llm_factory
from app.agent.sandbox import docker_sandbox
from app.agent.constants import WORKER_CODE


def _extract_code(raw: str) -> str:
    """从 LLM 输出中提取 Python 代码块。"""
    m = re.search(r"```python\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw.strip()


def code_worker_node(state: AgentState) -> dict:
    """代码 Worker：LLM 生成代码 → Docker 沙箱执行。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    if feedback:
        refinement_context = f"## 上一轮错误\n之前的代码执行失败，反馈如下：\n{feedback}\n请修复代码。"
    else:
        refinement_context = ""

    prompt = CODE_WORKER_PROMPT.replace("{refinement_context}", refinement_context).replace("{user_message}", user_message)
    response = llm.invoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)

    code = _extract_code(raw)

    try:
        result = docker_sandbox.run_code(code)
        if result.exit_code != 0:
            content = f"[代码执行错误]\n{result.stderr}"
            error = result.stderr
        else:
            content = result.stdout.strip() or "[代码执行完成，无输出]"
            error = None
        metadata = {"exit_code": result.exit_code, "timed_out": result.timed_out}
    except docker_sandbox.SandboxError as e:
        content = f"[沙箱错误] {e}"
        error = str(e)
        metadata = {"exit_code": -1, "timed_out": False}

    return {
        "worker_results": [
            {
                "worker": WORKER_CODE,
                "content": content,
                "error": error,
                "metadata": metadata,
            }
        ]
    }
