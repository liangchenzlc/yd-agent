from __future__ import annotations

from app.agent.storage.vector_store import FAISSStore
from app.agent.storage.graph_store import GraphStore
from app.agent.storage.kv_store import JsonKVStore


class StorageManager:
    """存储上下文管理器，管理所有存储后端的初始化/持久化/获取。"""

    def __init__(self, storage_dir: str, embedding_dim: int = 1024):
        self.entities_vdb = FAISSStore("entities", storage_dir, embedding_dim=embedding_dim)
        self.relationships_vdb = FAISSStore("relationships", storage_dir, embedding_dim=embedding_dim)
        self.chunks_vdb = FAISSStore("chunks", storage_dir, embedding_dim=embedding_dim)
        self.graph = GraphStore("knowledge", storage_dir)
        self.text_chunks_kv = JsonKVStore("text_chunks", storage_dir)

    async def initialize(self):
        """加载所有存储。"""
        self.entities_vdb.initialize()
        self.relationships_vdb.initialize()
        self.chunks_vdb.initialize()
        self.graph.initialize()
        self.text_chunks_kv.initialize()

    async def finalize(self):
        """持久化所有存储。"""
        self.entities_vdb.persist()
        self.relationships_vdb.persist()
        self.chunks_vdb.persist()
        self.graph.persist()
        self.text_chunks_kv.persist()

    def get_context(self) -> dict:
        """返回检索所需的存储实例字典。"""
        return {
            "entities_vdb": self.entities_vdb,
            "relationships_vdb": self.relationships_vdb,
            "chunks_vdb": self.chunks_vdb,
            "graph": self.graph,
            "text_chunks_kv": self.text_chunks_kv,
        }

    @property
    def has_documents(self) -> bool:
        """是否有已摄入的文档。"""
        return not self.entities_vdb.is_empty()
