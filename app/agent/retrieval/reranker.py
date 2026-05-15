from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def rerank(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    """用重排序模型对检索结果进行二阶段精排。

    调用阿里百炼 rerank API，返回重排后的文档列表（按相关性降序）。
    API 失败时降级返回原始顺序的前 top_k 条。
    """
    if not documents:
        return []

    texts = [_doc_text(doc) for doc in documents]
    settings = get_settings()
    api_key = settings.embedding_api_key or settings.llm_api_key
    base_url = settings.embedding_base_url or settings.llm_base_url

    if not api_key:
        return documents[:top_k]

    try:
        url = f"{base_url.rstrip('/')}/api/v1/services/rerank/text-rerank"
        payload = json.dumps({
            "model": settings.embedding_model,  # reuse embedding model config
            "query": query,
            "documents": texts,
            "top_n": min(top_k, len(texts)),
        }, ensure_ascii=False).encode("utf-8")

        req = Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")

        with urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            results = body.get("results", []) if "results" in body else \
                      body.get("data", {}).get("results", [])

        ranked: list[dict] = []
        for item in results:
            idx = item.get("index", item.get("doc_index", -1))
            relevance = item.get("relevance_score", item.get("score", 0))
            if 0 <= idx < len(documents):
                doc = dict(documents[idx])
                doc["rerank_score"] = round(relevance, 4)
                ranked.append(doc)

        ranked.sort(key=lambda d: d.get("rerank_score", 0), reverse=True)
        return ranked[:top_k]

    except Exception:
        logger.warning("Rerank API call failed, falling back to original order", exc_info=True)
        return documents[:top_k]


def _doc_text(doc: dict) -> str:
    """提取文档文本用于重排序。"""
    return doc.get("text") or doc.get("content", "")
