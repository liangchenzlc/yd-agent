from __future__ import annotations

import logging

import requests

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def rerank(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    """用 qwen3-vl-rerank 模型对检索结果进行二阶段精排。

    调用阿里百炼 rerank API，payload 格式：
      { model, input: { query, documents }, parameters: { top_n, return_documents } }

    API 失败时静默降级：返回原始顺序的前 top_k 条。
    不抛异常的原因：搜索服务的可用性不应影响整体回答流程。
    """
    if not documents:
        return []

    texts = [_doc_text(doc) for doc in documents]
    settings = get_settings()
    api_key = settings.llm_api_key

    if not api_key:
        return documents[:top_k]

    try:
        url = f"{settings.rerank_base_url.rstrip('/')}/api/v1/services/rerank/text-rerank/text-rerank"
        payload = {
            "model": settings.rerank_model,
            "input": {
                "query": query,
                "documents": texts,
            },
            "parameters": {
                "top_n": min(top_k, len(texts)),
                "return_documents": True,
            },
        }

        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()

        # DashScope response: {"output": {"results": [...]}}
        if "output" in body and "results" in body["output"]:
            results = body["output"]["results"]
        elif "results" in body:
            results = body["results"]
        else:
            results = body.get("data", {}).get("results", [])

        ranked: list[dict] = []
        for item in results:
            idx = item.get("index", -1)
            score = item.get("relevance_score", item.get("score", 0))
            if 0 <= idx < len(documents):
                doc = dict(documents[idx])
                doc["rerank_score"] = round(float(score), 4)
                ranked.append(doc)

        ranked.sort(key=lambda d: d.get("rerank_score", 0), reverse=True)
        return ranked[:top_k]

    except Exception:
        logger.warning("Rerank API call failed, falling back to original order", exc_info=True)
        return documents[:top_k]


def _doc_text(doc: dict) -> str:
    return doc.get("text") or doc.get("content", "")
