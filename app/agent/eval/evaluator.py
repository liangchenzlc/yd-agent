from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import json_repair

from app.agent.llm.factory import create_llm
from app.agent.prompts import EVALUATOR_PROMPT
from app.agent.eval.eval_manager import EvalManager
from app.agent.eval.hard_case_miner import generate_golden_answer


def _parse_evaluator_output(raw: str) -> dict:
    """解析评估 LLM 输出的 JSON，含容错回退。"""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if not m:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
    json_str = m.group(1) if m else raw

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        try:
            data = json_repair.loads(json_str)
        except Exception:
            return {
                "faithfulness": {"score": 0, "passed": False, "feedback": "JSON 解析失败"},
                "relevance": {"score": 0, "passed": False, "feedback": "JSON 解析失败"},
                "completeness": {"score": 0, "passed": False, "feedback": "JSON 解析失败"},
                "overall_score": 0,
                "is_hard_case": True,
                "summary": "评估输出解析失败",
            }
    if not isinstance(data, dict):
        return {
            "faithfulness": {"score": 0, "passed": False, "feedback": "非预期的 JSON 类型"},
            "relevance": {"score": 0, "passed": False, "feedback": "非预期的 JSON 类型"},
            "completeness": {"score": 0, "passed": False, "feedback": "非预期的 JSON 类型"},
            "overall_score": 0,
            "is_hard_case": True,
            "summary": "评估输出非 JSON 对象",
        }
    return data


async def run_evaluation(
    user_id: str,
    session_id: str | None,
    message: str,
    final_answer: str,
    worker_results: list[dict],
    refinement_count: int,
    eval_manager: EvalManager,
    hard_case_threshold: int = 5,
    golden_model: str | None = None,
) -> dict | None:
    """异步 LLM-as-Judge 评估，fire-and-forget 调用。

    评估 faithfulness / relevance / completeness 三维度，
    低分回答记录为 hard case，可选生成 golden answer。
    """
    try:
        # 格式化 Worker 结果
        if worker_results:
            lines = []
            for r in worker_results:
                w = r.get("worker", "unknown")
                c = r.get("content", "")
                e = r.get("error")
                status = "失败" if e else "成功"
                truncated = c[:500] + ("..." if len(c) > 500 else "")
                lines.append(f"### {w} ({status})\n{truncated}")
            worker_results_text = "\n\n".join(lines)
        else:
            worker_results_text = "[无 Worker 执行结果]"

        # 调用评估 LLM
        llm = create_llm(temperature=0)
        prompt = (
            EVALUATOR_PROMPT.replace("{user_message}", message)
            .replace("{final_answer}", final_answer)
            .replace("{worker_results}", worker_results_text)
        )
        response = await llm.ainvoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        result = _parse_evaluator_output(raw)

        # 提取各维度评分
        faithfulness = result.get("faithfulness", {})
        relevance = result.get("relevance", {})
        completeness = result.get("completeness", {})
        overall_score = result.get("overall_score")

        # 如果 overall_score 未提供或为 None，用三维度平均
        if overall_score is None:
            scores = [
                faithfulness.get("score", 0),
                relevance.get("score", 0),
                completeness.get("score", 0),
            ]
            overall_score = round(sum(scores) / 3)

        is_hard_case = overall_score < hard_case_threshold

        # 构建 eval run
        now = datetime.now(timezone.utc).isoformat()
        eval_item = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "answer": final_answer,
            "worker_results": [
                {"worker": r.get("worker", ""), "content": r.get("content", ""),
                 "error": r.get("error"), "metadata": r.get("metadata", {})}
                for r in worker_results
            ],
            "refinements": refinement_count,
            "overall_score": overall_score,
            "dimensions": [
                {"name": "faithfulness", "score": faithfulness.get("score", 0),
                 "passed": faithfulness.get("passed", False), "feedback": faithfulness.get("feedback", "")},
                {"name": "relevance", "score": relevance.get("score", 0),
                 "passed": relevance.get("passed", False), "feedback": relevance.get("feedback", "")},
                {"name": "completeness", "score": completeness.get("score", 0),
                 "passed": completeness.get("passed", False), "feedback": completeness.get("feedback", "")},
            ],
            "is_hard_case": is_hard_case,
            "timestamp": now,
        }

        run_id = await eval_manager.add_eval_run(eval_item)
        await eval_manager.update_stats(overall_score)

        # 难例处理
        if is_hard_case:
            golden = await generate_golden_answer(
                user_message=message,
                original_answer=final_answer,
                worker_results=worker_results,
                golden_model=golden_model,
            )
            await eval_manager.add_hard_case({
                "user_id": user_id,
                "message": message,
                "original_answer": final_answer,
                "golden_answer": golden,
                "score": overall_score,
                "timestamp": now,
                "reviewed": False,
            })

        return {"run_id": run_id, "overall_score": overall_score, "is_hard_case": is_hard_case}

    except Exception:
        # 评估失败不应影响主流程
        return None
