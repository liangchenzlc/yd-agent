from __future__ import annotations

import json
from typing import Any, Callable

from app.config.settings import get_settings


class RedisCache:
    """轻量级 Redis 缓存包装器，连接失败时优雅降级为空操作。"""

    def __init__(self):
        self._client: Any = None
        self._enabled = False

    def initialize(self):
        settings = get_settings()
        if not settings.redis_host:
            return
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password or None,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._enabled = True
        except Exception:
            self._enabled = False

    async def get(self, key: str) -> Any | None:
        if not self._enabled:
            return None
        try:
            val = await self._client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        if not self._enabled:
            return
        try:
            await self._client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        if not self._enabled:
            return
        try:
            await self._client.delete(key)
        except Exception:
            pass

    async def get_or_compute(self, key: str, factory: Callable, ttl: int = 300) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await factory() if callable(factory) else factory
        await self.set(key, value, ttl)
        return value

    async def incr(self, key: str, amount: int = 1, ttl: int = 86400) -> int | None:
        if not self._enabled:
            return None
        try:
            val = await self._client.incr(key, amount)
            await self._client.expire(key, ttl)
            return val
        except Exception:
            return None

    def close(self):
        if self._enabled and self._client:
            try:
                import asyncio
                asyncio.ensure_future(self._client.aclose())
            except Exception:
                pass
            self._enabled = False


redis_cache = RedisCache()
