from __future__ import annotations

import json
import logging
from typing import Any, Callable

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class RedisCache:
    """轻量级 Redis 缓存包装器，连接失败时优雅降级为空操作。"""

    def __init__(self):
        self._client: Any = None
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        """Redis 缓存是否可用。"""
        return self._enabled

    def initialize(self):
        settings = get_settings()
        if not settings.redis_host:
            logger.info("Redis not configured — running without cache")
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
            logger.warning("Redis connection failed — running without cache", exc_info=True)
            self._enabled = False

    async def get(self, key: str) -> Any | None:
        if not self._enabled:
            return None
        try:
            val = await self._client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception:
            logger.warning("Redis GET failed (key=%s)", key, exc_info=True)
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        if not self._enabled:
            return
        try:
            await self._client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception:
            logger.warning("Redis SET failed (key=%s)", key, exc_info=True)

    async def delete(self, key: str) -> None:
        if not self._enabled:
            return
        try:
            await self._client.delete(key)
        except Exception:
            logger.warning("Redis DELETE failed (key=%s)", key, exc_info=True)

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
            logger.warning("Redis INCR failed (key=%s)", key, exc_info=True)
            return None

    def close(self):
        if self._enabled and self._client:
            try:
                import asyncio

                asyncio.ensure_future(self._client.aclose())
            except Exception:
                logger.warning("Redis close failed", exc_info=True)
            self._enabled = False


redis_cache = RedisCache()
