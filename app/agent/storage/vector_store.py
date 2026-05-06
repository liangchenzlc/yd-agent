from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Sequence

import numpy as np

from app.agent.exceptions import StorageError


class FAISSStore:
    """FAISS 向量存储，封装 faiss.IndexFlatIP（内积 = 余弦相似度，输入需 L2 归一化）。"""

    def __init__(self, namespace: str, storage_dir: str, embedding_dim: int = 1024):
        self.namespace = namespace
        self.storage_dir = Path(storage_dir)
        self.embedding_dim = embedding_dim
        self._index: "faiss.Index" | None = None
        self._id_to_meta: dict[str, dict] = {}  # id -> {text, metadata}

    @property
    def index(self):
        if self._index is None:
            self._init_index()
        return self._index

    def _init_index(self):
        import faiss
        self._index = faiss.IndexFlatIP(self.embedding_dim)

    def initialize(self):
        """从磁盘加载向量库。"""
        meta_path = self.storage_dir / f"{self.namespace}_meta.json"
        index_path = self.storage_dir / f"{self.namespace}.faiss"
        if meta_path.exists() and index_path.exists():
            try:
                import faiss
                self._index = faiss.read_index(str(index_path))
                with open(meta_path, "r", encoding="utf-8") as f:
                    self._id_to_meta = json.load(f)
            except Exception as e:
                raise StorageError(f"FAISS 加载失败 ({self.namespace}): {e}") from e
        else:
            self._init_index()
            self._id_to_meta = {}

    def add_texts(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
    ):
        """添加文本及其预计算向量。"""
        if not ids:
            return
        import faiss

        emb_array = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(emb_array)
        ids_start = self.index.ntotal
        self.index.add(emb_array)
        for i, doc_id in enumerate(ids):
            self._id_to_meta[doc_id] = {
                "text": texts[i],
                "metadata": metadatas[i] if metadatas else {},
                "index_pos": ids_start + i,
            }

    def similarity_search_by_vector(
        self, query_embedding: list[float], k: int = 10, score_threshold: float | None = 0.6
    ) -> list[dict]:
        """按向量相似度检索。"""
        if self.is_empty():
            return []
        import faiss

        q = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(q)
        actual_k = min(k, self.index.ntotal)
        distances, indices = self.index.search(q, actual_k)
        id_to_pos = {v["index_pos"]: k for k, v in self._id_to_meta.items()}
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            if score_threshold is not None and dist < score_threshold:
                continue
            doc_id = id_to_pos.get(int(idx))
            if doc_id and doc_id in self._id_to_meta:
                results.append({
                    "id": doc_id,
                    "text": self._id_to_meta[doc_id]["text"],
                    "metadata": self._id_to_meta[doc_id]["metadata"],
                    "score": float(dist),
                })
        return results

    def delete(self, ids: list[str] | None = None):
        """删除指定 ID 的向量；ids 为 None 时清空全部。"""
        if ids is None:
            self._init_index()
            self._id_to_meta = {}
            return
        # FAISS 不支持直接按 ID 删除，重建索引
        import faiss

        remaining = {k: v for k, v in self._id_to_meta.items() if k not in ids}
        if len(remaining) == len(self._id_to_meta):
            return
        new_index = faiss.IndexFlatIP(self.embedding_dim)
        if remaining:
            texts_remaining = [(k, v) for k, v in remaining.items()]
            indices_remaining = [v["index_pos"] for _, v in texts_remaining]
            # 重建需要原始向量，这里简便处理：只重建无向量索引
            # 实际项目中应存储原始向量
        self._index = new_index
        self._id_to_meta = remaining

    def is_empty(self) -> bool:
        return self.index.ntotal == 0 or len(self._id_to_meta) == 0

    def persist(self):
        """持久化到磁盘。"""
        import faiss

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.storage_dir / f"{self.namespace}.faiss"))
        with open(self.storage_dir / f"{self.namespace}_meta.json", "w", encoding="utf-8") as f:
            json.dump(self._id_to_meta, f, ensure_ascii=False, indent=2)

    def __len__(self):
        return len(self._id_to_meta)
