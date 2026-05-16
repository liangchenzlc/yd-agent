from __future__ import annotations

import json
import logging
from typing import Any

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class RedisKVStore:
    """Redis KV 存储后端，替代 JsonKVStore。

    所有数据持久化在 Redis 中（RDB/AOF），无需手动调用 persist()。
    storage_dir 参数仅用于兼容原有接口，实际由 Redis 统一管理存储位置。

    不提供降级方案：Redis 连接失败时直接抛出异常，
    确保运维层面及时发现 Redis 不可用的问题。

    redis_client 参数用于测试注入（如 fakeredis.FakeRedis()），
    生产环境不传此参数，由 _connect() 自动创建连接。
    """

    def __init__(self, namespace: str, storage_dir: str = "", redis_client: Any = None):
        self.namespace = namespace
        self._prefix = f"kv:{namespace}:"
        self._redis: Any = redis_client

    def _connect(self) -> Any:
        import redis as sync_redis

        settings = get_settings()
        client = sync_redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            protocol=2,
        )
        client.ping()
        return client

    def initialize(self):
        if self._redis is None:
            self._redis = self._connect()

    def _key(self, k: str) -> str:
        return f"{self._prefix}{k}"

    def _unkey(self, prefixed: str) -> str:
        return prefixed[len(self._prefix):]

    def get_by_id(self, key: str) -> Any | None:
        val = self._redis.get(self._key(key))
        return json.loads(val) if val is not None else None

    def mget(self, keys: list[str]) -> list[Any | None]:
        if not keys:
            return []
        vals = self._redis.mget([self._key(k) for k in keys])
        return [json.loads(v) if v is not None else None for v in vals]

    def mset(self, pairs: dict[str, Any]):
        if not pairs:
            return
        pipe = self._redis.pipeline()
        for k, v in pairs.items():
            pipe.set(self._key(k), json.dumps(v, ensure_ascii=False))
        pipe.execute()

    def upsert(self, pairs: dict[str, Any]):
        self.mset(pairs)

    def mdelete(self, keys: list[str]):
        if not keys:
            return
        self._redis.delete(*[self._key(k) for k in keys])

    def keys(self) -> list[str]:
        cursor = 0
        result: list[str] = []
        while True:
            cursor, batch = self._redis.scan(cursor=cursor, match=f"{self._prefix}*", count=500)
            for key in batch:
                result.append(self._unkey(key))
            if cursor == 0:
                break
        return result

    def get_all(self) -> list[tuple[str, Any]]:
        """返回所有 (key, value) 对，供 EvalManager 等需要全量扫描的场景使用。

        注意：对大量键值对（>1 万），此操作会阻塞。如成为瓶颈，
        应考虑在 Redis 侧使用专门的聚合查询。
        """
        keys = self.keys()
        vals = self.mget(keys)
        return [(k, v) for k, v in zip(keys, vals) if v is not None]

    def clear(self):
        """删除命名空间下的所有键，用于 EvalManager 的批量清理操作。"""
        keys = self.keys()
        if keys:
            self._redis.delete(*[self._key(k) for k in keys])

    def persist(self):
        pass

    def __len__(self) -> int:
        count = 0
        cursor = 0
        while True:
            cursor, batch = self._redis.scan(cursor=cursor, match=f"{self._prefix}*", count=500)
            count += len(batch)
            if cursor == 0:
                break
        return count
