from __future__ import annotations

import logging
from pathlib import Path

from app.agent.storage.bm25_store import BM25Store
from app.agent.storage.redis_kv_store import RedisKVStore
from app.agent.storage.vector_store import FAISSStore

logger = logging.getLogger(__name__)


class StorageManager:
    """存储上下文管理器，管理所有存储后端的初始化/持久化/获取。

    统一管理三个存储后端：FAISS（向量搜索）、BM25（关键词搜索）、JSON KV（元数据/文本缓存）。
    三者共享同一 storage_dir，确保数据隔离（每个 tenant 占用独立目录）。
    """

    _instances: dict[str, StorageManager] = {}
    MAX_CACHED_INSTANCES = 20

    def __init__(self, storage_dir: str, embedding_dim: int = 1024):
        self.storage_dir = storage_dir
        self.tenant_id = Path(storage_dir).name  # 从目录名提取租户标识
        self.chunks_vdb = FAISSStore("chunks", storage_dir, embedding_dim=embedding_dim)
        self.bm25_store = BM25Store("bm25", storage_dir)
        # 每个租户使用独立的 Redis 命名空间，确保检索时不会跨租户查到其他租户的文档
        self.text_chunks_kv = RedisKVStore(f"text_chunks:{self.tenant_id}")

    @classmethod
    def get_cached(cls, storage_dir: str, embedding_dim: int = 1024) -> StorageManager:
        """从缓存获取或创建 StorageManager，避免重复加载 FAISS/BM25/KV。

        单例缓存的原因：
        1. FAISS 索引加载到内存后约 100MB-1GB，多次加载浪费严重
        2. BM25 的倒排索引构建成本高
        3. 同一进程内的多个请求应该共享同一份存储

        缓存淘汰策略 LRU（近似）：当实例数超过 MAX_CACHED_INSTANCES 时，
        驱逐最早创建的实例（dict 是插入有序的，iter 返回的第一个即最早插入的）。
        注意这只是粗略的 LRU，访问时不更新顺序——但对于 20 个上限已经足够。
        """
        if storage_dir in cls._instances:
            logger.debug("StorageManager cache HIT for %s", storage_dir)
            return cls._instances[storage_dir]
        if len(cls._instances) >= cls.MAX_CACHED_INSTANCES:
            oldest = next(iter(cls._instances))
            logger.debug("Evicting oldest StorageManager cache: %s", oldest)
            # 驱逐前先 finalize，确保 FAISS 索引和 BM25 数据落盘
            cls._instances.pop(oldest).finalize()
        logger.debug("StorageManager cache MISS for %s, loading...", storage_dir)
        instance = cls(storage_dir=storage_dir, embedding_dim=embedding_dim)
        instance.initialize()
        cls._instances[storage_dir] = instance
        return instance

    @classmethod
    def invalidate_cache(cls, storage_dir: str) -> None:
        """文档增删时调用，清除指定 storage_dir 的缓存。

        文档变更后，FAISS 和 BM25 的索引已过时，必须强制下次请求重建。
        注意：调用方需确保已通过其他方式持久化当前索引，否则直接 pop
        会导致未保存的变更丢失。
        """
        cls._instances.pop(storage_dir, None)

    def initialize(self):
        """加载所有存储。"""
        self.chunks_vdb.initialize()
        self.bm25_store.initialize()
        self.text_chunks_kv.initialize()

    def finalize(self):
        """持久化所有存储。"""
        self.chunks_vdb.persist()
        self.bm25_store.persist()
        self.text_chunks_kv.persist()

    def get_context(self) -> dict:
        """返回检索所需的存储实例字典。"""
        return {
            "chunks_vdb": self.chunks_vdb,
            "bm25_store": self.bm25_store,
            "text_chunks_kv": self.text_chunks_kv,
        }

    @property
    def has_documents(self) -> bool:
        """是否有已摄入的文档。

        同时检查向量库（FAISS）和 KV 存储，因为：
        - FAISS 为空不一定代表无文档（可能文档刚删除或 FAISS 索引损坏）
        - KV 中存有 doc_meta 前缀的键则说明至少有一条文档元数据
        两者任一存在即认为有文档，避免空库时搜索引擎抛出异常。
        """
        if not self.chunks_vdb.is_empty():
            return True
        return any(key.startswith("doc_meta:") for key in self.text_chunks_kv.keys())
