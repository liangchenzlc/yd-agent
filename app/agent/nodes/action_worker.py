import json
import re

import httpx

from app.agent.state import AgentState
from app.agent.prompts import ACTION_WORKER_PROMPT
from app.agent.llm import factory as llm_factory
from app.agent.constants import WORKER_ACTION


def _parse_action(raw: str) -> dict:
    """解析 Action Worker 的 LLM 输出。"""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if not m:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
    json_str = m.group(1) if m else raw

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        from json_repair import repair_json
        try:
            return json.loads(repair_json(json_str))
        except Exception:
            return {}


def action_worker_node(state: AgentState) -> dict:
    """动作 Worker：LLM 生成 REST API 调用规格 → httpx 执行。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    if feedback:
        refinement_context = f"## 上一轮错误\n{feedback}\n请修正 API 调用。"
    else:
        refinement_context = ""

    prompt = ACTION_WORKER_PROMPT.replace("{refinement_context}", refinement_context).replace("{user_message}", user_message)
    response = llm.invoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)

    spec = _parse_action(raw)

    method = spec.get("method", "GET").upper()
    url = spec.get("url", "")
    headers = spec.get("headers", {})
    body = spec.get("body", None)

    if not url:
        return {
            "worker_results": [
                {
                    "worker": WORKER_ACTION,
                    "content": "[API 调用失败：未能从 LLM 输出中解析出有效 URL]",
                    "error": "未能解析 URL",
                    "metadata": {},
                }
            ]
        }

    try:
        with httpx.Client(timeout=30) as client:
            r = client.request(method=method, url=url, headers=headers, json=body)
            r.raise_for_status()
            content = r.text[:2000]  # 截断过长响应
            error = None
            metadata = {"status_code": r.status_code, "url": url, "method": method}
    except httpx.HTTPStatusError as e:
        content = f"[HTTP 错误] {e.response.status_code}: {e.response.text[:500]}"
        error = str(e)
        metadata = {"status_code": e.response.status_code, "url": url, "method": method}
    except httpx.RequestError as e:
        content = f"[请求失败] {e}"
        error = str(e)
        metadata = {"url": url, "method": method}

    return {
        "worker_results": [
            {
                "worker": WORKER_ACTION,
                "content": content,
                "error": error,
                "metadata": metadata,
            }
        ]
    }
