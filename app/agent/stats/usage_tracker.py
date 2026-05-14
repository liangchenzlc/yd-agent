from __future__ import annotations

from datetime import datetime, timezone

from app.agent.storage.redis_cache import redis_cache


def _date_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def track_api_call(user_id: int, tenant_id: str, endpoint: str) -> None:
    """记录一次 API 调用，自增 Redis 计数器。"""
    date = _date_key()
    await redis_cache.incr(f"stats:{date}:api:total", ttl=86400 * 8)
    await redis_cache.incr(f"stats:{date}:api:user:{user_id}", ttl=86400 * 8)
    await redis_cache.incr(f"stats:{date}:api:tenant:{tenant_id}", ttl=86400 * 8)
    await redis_cache.incr(f"stats:{date}:api:endpoint:{endpoint}", ttl=86400 * 8)


async def track_llm_tokens(user_id: int, model: str, input_tokens: int, output_tokens: int) -> None:
    """记录 LLM token 消耗。"""
    date = _date_key()
    total = input_tokens + output_tokens
    await redis_cache.incr(f"stats:{date}:tokens:total", amount=total, ttl=86400 * 8)
    await redis_cache.incr(f"stats:{date}:tokens:input", amount=input_tokens, ttl=86400 * 8)
    await redis_cache.incr(f"stats:{date}:tokens:output", amount=output_tokens, ttl=86400 * 8)
    await redis_cache.incr(f"stats:{date}:tokens:user:{user_id}", amount=total, ttl=86400 * 8)
    await redis_cache.incr(f"stats:{date}:tokens:model:{model}", amount=total, ttl=86400 * 8)


async def get_daily_stats(date: str | None = None) -> dict:
    """获取指定日期的用量统计。"""
    date = date or _date_key()
    api_total = await redis_cache.get(f"stats:{date}:api:total") or 0
    token_total = await redis_cache.get(f"stats:{date}:tokens:total") or 0
    token_input = await redis_cache.get(f"stats:{date}:tokens:input") or 0
    token_output = await redis_cache.get(f"stats:{date}:tokens:output") or 0

    return {
        "date": date,
        "api_calls": api_total,
        "tokens": {"total": token_total, "input": token_input, "output": token_output},
    }


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中英文混合约 4 字符/token）。"""
    return max(1, len(text) // 4)
