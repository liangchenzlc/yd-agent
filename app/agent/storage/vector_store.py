from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.agent.exceptions import StorageError


class FAISSStore:
    """FAISS vector store backed by IndexFlatIP.

    Vectors are normalized before insertion, so inner product behaves as cosine
    similarity. Embeddings are persisted in metadata so partial deletes can
    rebuild the index without re-calling the embedding service.
    """

    def __init__(self, namespace: str, storage_dir: str, embedding_dim: int = 1024):
        self.namespace = namespace
        self.storage_dir = Path(storage_dir)
        self.embedding_dim = embedding_dim
        self._index: "faiss.Index" | None = None
        self._id_to_meta: dict[str, dict] = {}

    @property
    def index(self):
        if self._index is None:
            self._init_index()
        return self._index

    def _init_index(self):
        import faiss

        self._index = faiss.IndexFlatIP(self.embedding_dim)

    def initialize(self):
        meta_path = self.storage_dir / f"{self.namespace}_meta.json"
        index_path = self.storage_dir / f"{self.namespace}.faiss"
        if meta_path.exists() and index_path.exists():
            try:
                import faiss

                self._index = faiss.read_index(str(index_path))
                with open(meta_path, "r", encoding="utf-8") as f:
                    self._id_to_meta = json.load(f)
            except Exception as e:
                raise StorageError(f"FAISS load failed ({self.namespace}): {e}") from e
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
        if not ids:
            return
        if not (len(ids) == len(texts) == len(embeddings)):
            raise StorageError("ids, texts, embeddings lengths must match")

        existing_ids = [item_id for item_id in ids if item_id in self._id_to_meta]
        if existing_ids:
            self.delete(existing_ids)

        import faiss

        emb_array = np.array(embeddings, dtype=np.float32)
        if emb_array.ndim != 2 or emb_array.shape[1] != self.embedding_dim:
            raise StorageError(
                f"embedding dimension mismatch: {emb_array.shape}; expected (*, {self.embedding_dim})"
            )

        faiss.normalize_L2(emb_array)
        ids_start = self.index.ntotal
        self.index.add(emb_array)
        for i, doc_id in enumerate(ids):
            self._id_to_meta[doc_id] = {
                "text": texts[i],
                "metadata": metadatas[i] if metadatas else {},
                "index_pos": ids_start + i,
                "embedding": emb_array[i].tolist(),
            }

    def similarity_search_by_vector(
        self,
        query_embedding: list[float],
        k: int = 10,
        score_threshold: float | None = 0.6,
    ) -> list[dict]:
        if self.is_empty():
            return []

        import faiss

        q = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(q)
        actual_k = min(k, self.index.ntotal)
        distances, indices = self.index.search(q, actual_k)
        id_by_pos = {v["index_pos"]: k for k, v in self._id_to_meta.items()}
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            if score_threshold is not None and dist < score_threshold:
                continue
            doc_id = id_by_pos.get(int(idx))
            if doc_id and doc_id in self._id_to_meta:
                results.append(
                    {
                        "id": doc_id,
                        "text": self._id_to_meta[doc_id]["text"],
                        "metadata": self._id_to_meta[doc_id]["metadata"],
                        "score": float(dist),
                    }
                )
        return results

    def delete(self, ids: list[str] | None = None):
        if ids is None:
            self._init_index()
            self._id_to_meta = {}
            return

        remaining = {k: v for k, v in self._id_to_meta.items() if k not in ids}
        if len(remaining) == len(self._id_to_meta):
            return

        self._rebuild_from_meta(remaining)

    def delete_by_metadata(self, key: str, value) -> list[str]:
        ids = [
            item_id
            for item_id, meta in self._id_to_meta.items()
            if meta.get("metadata", {}).get(key) == value
        ]
        if ids:
            self.delete(ids)
        return ids

    def _rebuild_from_meta(self, items: dict[str, dict]):
        import faiss

        new_index = faiss.IndexFlatIP(self.embedding_dim)
        new_meta: dict[str, dict] = {}
        if items:
            ordered_items = sorted(
                items.items(),
                key=lambda item: item[1].get("index_pos", 0),
            )
            vectors = []
            ids_in_order = []
            for doc_id, meta in ordered_items:
                emb = meta.get("embedding")
                if emb is None:
                    old_pos = meta.get("index_pos")
                    if old_pos is None:
                        continue
                    emb = self.index.reconstruct(int(old_pos)).tolist()
                vectors.append(emb)
                ids_in_order.append(doc_id)

            if vectors:
                emb_array = np.array(vectors, dtype=np.float32)
                faiss.normalize_L2(emb_array)
                new_index.add(emb_array)
                for pos, doc_id in enumerate(ids_in_order):
                    old_meta = items[doc_id]
                    new_meta[doc_id] = {
                        "text": old_meta.get("text", ""),
                        "metadata": old_meta.get("metadata", {}),
                        "index_pos": pos,
                        "embedding": emb_array[pos].tolist(),
                    }

        self._index = new_index
        self._id_to_meta = new_meta

    def is_empty(self) -> bool:
        return self.index.ntotal == 0 or len(self._id_to_meta) == 0

    def persist(self):
        import faiss

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.storage_dir / f"{self.namespace}.faiss"))
        with open(self.storage_dir / f"{self.namespace}_meta.json", "w", encoding="utf-8") as f:
            json.dump(self._id_to_meta, f, ensure_ascii=False, indent=2)

    def __len__(self):
        return len(self._id_to_meta)
