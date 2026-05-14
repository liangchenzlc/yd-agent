from __future__ import annotations

from datetime import datetime, timezone

from app.agent.llm import factory as llm_factory
from app.agent.prompts import EVALUATOR_PROMPT, fill_prompt
from app.agent.eval.eval_manager import EvalManager
from app.agent.eval.hard_case_miner import generate_golden_answer
from app.domain.llm_output import EvaluationOutput


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
    """异步 LLM-as-Judge 评估，fire-and-forget 调用。"""
    try:
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

        llm = llm_factory.create_llm(temperature=0)
        prompt = fill_prompt(EVALUATOR_PROMPT,
            user_message=message,
            final_answer=final_answer,
            worker_results=worker_results_text,
        )

        structured_llm = llm.with_structured_output(EvaluationOutput)
        result: EvaluationOutput = await structured_llm.ainvoke(prompt)

        scores = [
            result.faithfulness.score,
            result.relevance.score,
            result.completeness.score,
        ]
        overall_score = result.overall_score if result.overall_score else round(sum(scores) / 3)
        is_hard_case = overall_score < hard_case_threshold

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
                {"name": "faithfulness", "score": result.faithfulness.score,
                 "passed": result.faithfulness.passed, "feedback": result.faithfulness.feedback},
                {"name": "relevance", "score": result.relevance.score,
                 "passed": result.relevance.passed, "feedback": result.relevance.feedback},
                {"name": "completeness", "score": result.completeness.score,
                 "passed": result.completeness.passed, "feedback": result.completeness.feedback},
            ],
            "is_hard_case": is_hard_case,
            "timestamp": now,
        }

        run_id = await eval_manager.add_eval_run(eval_item)
        await eval_manager.update_stats(overall_score)

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
        return None
