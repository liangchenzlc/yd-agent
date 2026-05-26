from __future__ import annotations

from datetime import datetime, timezone

from app.agent.storage.redis_cache import redis_cache
from app.web.db import db


def _date_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def track_api_call(user_id: int, tenant_id: str, endpoint: str) -> None:
    """记录一次 API 调用，双写 Redis + SQLite 确保数据持久化。"""
    date = _date_key()
    if redis_cache.is_enabled:
        await redis_cache.incr(f"stats:{date}:api:total", ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:api:user:{user_id}", ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:api:tenant:{tenant_id}", ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:api:endpoint:{endpoint}", ttl=86400 * 8)
    # 始终持久化到 SQLite
    db.upsert_usage_stat(date, "api", "total")
    db.upsert_usage_stat(date, "api", f"user:{user_id}")
    db.upsert_usage_stat(date, "api", f"tenant:{tenant_id}")
    db.upsert_usage_stat(date, "api", f"endpoint:{endpoint}")


async def track_llm_tokens(user_id: int, model: str, input_tokens: int, output_tokens: int,
                           tenant_id: str = "default") -> None:
    """记录 LLM token 消耗，双写 Redis + SQLite。"""
    date = _date_key()
    total = input_tokens + output_tokens
    if redis_cache.is_enabled:
        await redis_cache.incr(f"stats:{date}:tokens:total", amount=total, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:input", amount=input_tokens, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:output", amount=output_tokens, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:user:{user_id}", amount=total, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:model:{model}", amount=total, ttl=86400 * 8)
        await redis_cache.incr(f"stats:{date}:tokens:tenant:{tenant_id}", amount=total, ttl=86400 * 8)
    # 始终持久化到 SQLite
    db.upsert_usage_stat(date, "tokens", "total", total)
    db.upsert_usage_stat(date, "tokens", "input", input_tokens)
    db.upsert_usage_stat(date, "tokens", "output", output_tokens)
    db.upsert_usage_stat(date, "tokens", f"user:{user_id}", total)
    db.upsert_usage_stat(date, "tokens", f"model:{model}", total)
    db.upsert_usage_stat(date, "tokens", f"tenant:{tenant_id}", total)


async def get_daily_stats(date: str | None = None, tenant_id: str | None = None) -> dict:
    """获取指定日期的用量统计。tenant_id 非 None 时返回该租户的统计。

    优先读 Redis 热缓存，无数据时回退到 SQLite（兜底持久化）。
    """
    date = date or _date_key()

    def _rkey(suffix: str) -> str:
        return f"stats:{date}:{suffix}"

    def _db_get(cat: str, key: str) -> int:
        return db.get_usage_stat(date, cat, key)

    async def _redis_or_db(cat: str, key: str, redis_suffix: str) -> int:
        if redis_cache.is_enabled:
            val = await redis_cache.get(_rkey(redis_suffix))
            if val is not None:
                return val
        return _db_get(cat, key)

    if tenant_id:
        api_total = await _redis_or_db("api", f"tenant:{tenant_id}", f"api:tenant:{tenant_id}")
        token_total = await _redis_or_db("tokens", f"tenant:{tenant_id}", f"tokens:tenant:{tenant_id}")
        return {"date": date, "api_calls": api_total, "tokens": {"total": token_total}}

    api_total = await _redis_or_db("api", "total", "api:total")
    token_total = await _redis_or_db("tokens", "total", "tokens:total")
    token_input = await _redis_or_db("tokens", "input", "tokens:input")
    token_output = await _redis_or_db("tokens", "output", "tokens:output")

    return {
        "date": date,
        "api_calls": api_total,
        "tokens": {"total": token_total, "input": token_input, "output": token_output},
    }


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中英文混合约 4 字符/token）。"""
    return max(1, len(text) // 4)
