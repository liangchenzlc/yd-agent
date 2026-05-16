from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    """分词：英文按单词分词并小写，CJK 拆单字。

    rank_bm25 库的 BM25Okapi 不内置 CJK 分词支持。
    对中文拆单字虽然粒度粗，但 BM25 的词频（TF）统计对单字级别的匹配仍然有效，
    比完全不切词（把整段中文当做一个 token）要好得多。
    英文部分保留连字符连接词（如 state-of-the-art）作为一个整体 token。
    """
    tokens: list[str] = []
    for eng in re.findall(r"[a-zA-Z0-9]+(?:[+_-][a-zA-Z0-9]+)*", text):
        tokens.append(eng.lower())
    # CJK 拆单字：单字是 BM25 能理解的最小原子单位
    for cjk in re.findall(r"[一-鿿]+", text):
        tokens.extend(cjk)
    return tokens


class BM25Store:
    """BM25 关键词检索存储后端。

    核心设计决策：
    - 内部维护两份数据：语料库列表（可持久化为 JSON）和 BM25Okapi 实例（内存索引）
    - 持久化只写语料库 JSON，BM25 索引在 initialize() 时重建。
      这是因为 BM25Okapi 不支持序列化，只能保存原始语料后重建。
    - 任何增删操作都触发 _rebuild_index()，重建开销大约 O(N*L)，
      N=文档数，L=平均长度。对数百文档级别无感（<100ms），
      但大规模场景（>10万文档）需改为增量更新策略。

    与 FAISS 和 KV 存储一起构成混合检索的三大支柱。
    """

    def __init__(self, namespace: str, storage_dir: str):
        self.namespace = namespace
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        # 语料库文件命名约定：{namespace}_bm25.json
        # namespace 通常为 "bm25"，不同 StorageManager 实例的目录不同保证隔离
        self._corpus_path = self._dir / f"{namespace}_bm25.json"

        self._corpus: list[dict[str, Any]] = []
        self._bm25: BM25Okapi | None = None

    # ---- 公共 API ----

    def initialize(self) -> None:
        """从磁盘加载语料库并重建 BM25 索引。

        重建 BM25 索引（_rebuild_index）在加载后进行，而不是持久化 BM25 对象本身，
        因为 BM25Okapi 实例不可序列化（内部包含大量数组对象）。
        """
        if self._corpus_path.exists():
            with self._corpus_path.open("r", encoding="utf-8") as f:
                self._corpus = json.load(f)
        self._rebuild_index()

    def persist(self) -> None:
        """将语料库持久化到磁盘。"""
        with self._corpus_path.open("w", encoding="utf-8") as f:
            json.dump(self._corpus, f, ensure_ascii=False, indent=2)

    def add_texts(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        """添加文本到 BM25 索引。

        每次添加后全量重建索引。对于批量添加，调用方应自行合并成一次调用，
        避免多次重建带来的性能浪费。
        """
        for i, tid in enumerate(ids):
            self._corpus.append({
                "id": tid,
                "text": texts[i],
                "metadata": metadatas[i] if metadatas else {},
            })
        self._rebuild_index()

    def search(self, query: str, k: int = 10) -> list[dict[str, Any]]:
        """BM25 关键词检索，返回降序排序结果。

        过滤 score <= 0 的结果（完全不匹配），避免低质量片段进入下游。
        返回格式: [{id, text, metadata, score}, ...]
        """
        if not self._bm25 or not self._corpus:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:k]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            results.append({
                "id": self._corpus[idx]["id"],
                "text": self._corpus[idx]["text"],
                "metadata": dict(self._corpus[idx]["metadata"]),
                "score": scores[idx],
            })
        return results

    def delete(self, ids: list[str] | None = None) -> None:
        """删除指定 ID 的文档。"""
        if not ids:
            return
        ids_set = set(ids)
        self._corpus = [c for c in self._corpus if c["id"] not in ids_set]
        self._rebuild_index()

    def delete_by_metadata(self, key: str, value: Any) -> list[str]:
        """删除 metadata[key] == value 的所有条目，返回被删 ID 列表。

        线性扫描全语料库，对于小规模场景（<1万条）性能可接受。
        返回被删 ID 列表供调用方同步删除其他存储后端中的对应条目。
        """
        deleted = []
        remaining = []
        for c in self._corpus:
            if c.get("metadata", {}).get(key) == value:
                deleted.append(c["id"])
            else:
                remaining.append(c)
        if deleted:
            self._corpus = remaining
            self._rebuild_index()
        return deleted

    def is_empty(self) -> bool:
        return len(self._corpus) == 0

    def __len__(self) -> int:
        return len(self._corpus)

    # ---- 内部 ----

    def _rebuild_index(self) -> None:
        """从当前语料库重建 BM25Okapi 索引。

        全量重建而非增量更新的原因：BM25Okapi 不提供增量添加 API，
        每次必须传入完整 tokenized_corpus。
        这是 rank_bm25 库的设计局限，大规模场景下需要考虑替换为 Elasticsearch 等方案。
        """
        if not self._corpus:
            self._bm25 = None
            return
        tokenized_corpus = [_tokenize(c["text"]) for c in self._corpus]
        self._bm25 = BM25Okapi(tokenized_corpus)
