import json
import re

from app.agent.state import AgentState
from app.agent.prompts import SUPERVISOR_PROMPT
from app.agent.llm import factory as llm_factory
from app.agent.constants import ALL_WORKERS


def _parse_supervisor_output(raw: str, user_message: str) -> tuple[list[str], str]:
    """解析 Supervisor LLM 输出的 JSON。"""
    workers: list[str] = []
    reasoning: str = ""

    # 尝试从 JSON 代码块中提取
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if not m:
        # 尝试直接匹配 JSON 对象
        m = re.search(r"\{.*\}", raw, re.DOTALL)
    json_str = m.group(1) if m else raw

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 使用 json-repair 恢复
        from json_repair import repair_json
        try:
            data = json.loads(repair_json(json_str))
        except Exception:
            return (["summary"], "Supervisor 输出解析失败，默认路由到 summary Worker")

    workers = data.get("workers", ["summary"])
    reasoning = data.get("reasoning", "")

    # 过滤不合法 Worker
    workers = [w for w in workers if w in ALL_WORKERS]
    if not workers:
        workers = ["summary"]
        reasoning = "未选中有效 Worker，默认使用 summary"

    return (workers, reasoning)


def supervisor_node(state: AgentState) -> dict:
    """Supervisor 节点：分析用户意图，决定调度哪些 Worker。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    prompt = SUPERVISOR_PROMPT.replace("{user_message}", user_message)
    response = llm.invoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)

    workers, reasoning = _parse_supervisor_output(raw, user_message)

    return {
        "worker_assignments": workers,
        "dispatch_reasoning": reasoning,
        "worker_results": [],  # 重置 Worker 结果
    }
