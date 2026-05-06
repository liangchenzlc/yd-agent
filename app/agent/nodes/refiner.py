import json
import re

from app.agent.state import AgentState
from app.agent.prompts import REFINER_PROMPT
from app.agent.llm import factory as llm_factory
from app.agent.constants import ALL_WORKERS, REFINER_SCORE_THRESHOLD, MAX_REFINEMENTS


def _parse_refiner_output(raw: str) -> dict:
    """解析 Refiner LLM 输出的 JSON。"""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if not m:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
    json_str = m.group(1) if m else raw

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        from json_repair import repair_json
        try:
            data = json.loads(repair_json(json_str))
        except Exception:
            return {"score": 10, "feedback": "", "retarget_workers": []}

    return data


def refiner_node(state: AgentState) -> dict:
    """Refiner 节点：评估回答质量，决定是否重试。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""
    final_answer = state.get("final_answer", "")
    worker_results = state.get("worker_results", [])
    refinement_count = state.get("refinement_count", 0)

    # 格式化 Worker 结果
    results_text = "\n".join(
        f"[{r.get('worker', '?')}] {r.get('content', '')[:500]}"
        for r in worker_results
    ) if worker_results else "[无]"

    prompt = REFINER_PROMPT.replace("{user_message}", user_message).replace("{worker_results}", results_text).replace("{final_answer}", final_answer).replace("{refinement_count}", str(refinement_count))
    response = llm.invoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)

    data = _parse_refiner_output(raw)

    score = data.get("score", 10)
    feedback = data.get("feedback", "")
    retarget = data.get("retarget_workers", [])

    # 过滤非法 Worker
    retarget = [w for w in retarget if w in ALL_WORKERS]

    if score < REFINER_SCORE_THRESHOLD and refinement_count < MAX_REFINEMENTS and retarget:
        return {
            "refinement_needed": True,
            "refinement_feedback": feedback,
            "refinement_targets": retarget,
            "refinement_count": refinement_count + 1,
        }
    else:
        return {
            "refinement_needed": False,
            "refinement_count": refinement_count,
        }
