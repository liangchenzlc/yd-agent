from __future__ import annotations

import asyncio
import logging

from app.agent.eval.eval_manager import EvalManager

logger = logging.getLogger(__name__)


async def schedule_eval_maintenance(
    eval_manager: EvalManager,
    interval_hours: int = 6,
    retention_days: int = 30,
    max_runs: int = 200,
):
    """后台定时清理过期评估记录并限制总数。"""
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            await eval_manager.purge_expired_runs(retention_days)
            await eval_manager.cap_max_runs(max_runs)
        except Exception:
            logger.warning("Eval maintenance task failed", exc_info=True)
