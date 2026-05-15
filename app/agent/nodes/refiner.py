from __future__ import annotations

import logging

from app.agent.state import AgentState
from app.agent.prompts import REFINER_PROMPT, fill_prompt
from app.agent.llm import factory as llm_factory
from app.agent.constants import ALL_WORKERS, REFINER_SCORE_THRESHOLD, MAX_REFINEMENTS
from app.domain.llm_output import RefinerOutput

logger = logging.getLogger(__name__)


def refiner_node(state: AgentState) -> dict:
    """Refiner 节点：评估回答质量，决定是否重试。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""
    final_answer = state.get("final_answer", "")
    current_refinement = state.get("refinement_count", 0)
    worker_results = [
        r for r in state.get("worker_results", [])
        if r.get("metadata", {}).get("refinement_count", 0) == current_refinement
    ]
    refinement_count = current_refinement

    results_text = "\n".join(
        f"[{r.get('worker', '?')}] {r.get('content', '')[:500]}"
        for r in worker_results
    ) if worker_results else "[无]"

    prompt = fill_prompt(REFINER_PROMPT,
        user_message=user_message,
        worker_results=results_text,
        final_answer=final_answer,
        refinement_count=str(refinement_count),
    )

    try:
        structured_llm = llm.with_structured_output(RefinerOutput)
        result: RefinerOutput = structured_llm.invoke(prompt)
    except Exception:
        logger.warning("Refiner LLM call failed, defaulting to pass (score=7)", exc_info=True)
        result = RefinerOutput(score=7)  # 解析失败时默认通过

    retarget = [w for w in result.retarget_workers if w in ALL_WORKERS]

    if result.score < REFINER_SCORE_THRESHOLD and refinement_count < MAX_REFINEMENTS and retarget:
        return {
            "refinement_needed": True,
            "refinement_feedback": result.feedback,
            "refinement_targets": retarget,
            "refinement_count": refinement_count + 1,
        }

    return {
        "refinement_needed": False,
        "refinement_count": refinement_count,
    }
