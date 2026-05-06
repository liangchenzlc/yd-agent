from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.agent.memory.memory_manager import MemoryManager


async def prune_expired_memories(memory_manager: MemoryManager):
    """剪枝过期的工作记忆（按 24h TTL）。"""
    await memory_manager.prune_expired_memories()


async def schedule_pruning(memory_manager: MemoryManager, interval_seconds: int = 3600):
    """后台定时剪枝（每小时一次）。"""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await prune_expired_memories(memory_manager)
        except Exception:
            pass
