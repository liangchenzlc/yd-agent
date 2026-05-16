from __future__ import annotations

from datetime import datetime, timezone

from app.agent.storage.redis_cache import redis_cache
from app.web.db import db


def _date_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def track_api_call(user_id: int, tenant_id: str, endpoint: str) -> None:
    """记录一次 API 调用，自增计数器。"""
    date = _date_key()
    if redis_cache._enabled:
        await redis_cache.incr(f"stats:{date}:api:total", ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:api:user:{user_id}", ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:api:tenant:{tenant_id}", ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:api:endpoint:{endpoint}", ttl=86400 * 8)
    else:
        db.upsert_usage_stat(date, "api", "total")
        db.upsert_usage_stat(date, "api", f"user:{user_id}")
        db.upsert_usage_stat(date, "api", f"tenant:{tenant_id}")
        db.upsert_usage_stat(date, "api", f"endpoint:{endpoint}")


async def track_llm_tokens(user_id: int, model: str, input_tokens: int, output_tokens: int) -> None:
    """记录 LLM token 消耗。"""
    date = _date_key()
    total = input_tokens + output_tokens
    if redis_cache._enabled:
        await redis_cache.incr(f"stats:{date}:tokens:total", amount=total, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:input", amount=input_tokens, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:output", amount=output_tokens, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:user:{user_id}", amount=total, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:model:{model}", amount=total, ttl=86400 * 8)
    else:
        db.upsert_usage_stat(date, "tokens", "total", total)
        db.upsert_usage_stat(date, "tokens", "input", input_tokens)
        db.upsert_usage_stat(date, "tokens", "output", output_tokens)
        db.upsert_usage_stat(date, "tokens", f"user:{user_id}", total)
        db.upsert_usage_stat(date, "tokens", f"model:{model}", total)


async def get_daily_stats(date: str | None = None) -> dict:
    """获取指定日期的用量统计。"""
    date = date or _date_key()

    if redis_cache._enabled:
        api_total = await redis_cache.get(f"stats:{date}:api:total") or 0
        token_total = await redis_cache.get(f"stats:{date}:tokens:total") or 0
        token_input = await redis_cache.get(f"stats:{date}:tokens:input") or 0
        token_output = await redis_cache.get(f"stats:{date}:tokens:output") or 0
    else:
        api_total = db.get_usage_stat(date, "api", "total")
        token_total = db.get_usage_stat(date, "tokens", "total")
        token_input = db.get_usage_stat(date, "tokens", "input")
        token_output = db.get_usage_stat(date, "tokens", "output")

    return {
        "date": date,
        "api_calls": api_total,
        "tokens": {"total": token_total, "input": token_input, "output": token_output},
    }


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中英文混合约 4 字符/token）。"""
    return max(1, len(text) // 4)
