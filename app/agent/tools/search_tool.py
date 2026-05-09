from __future__ import annotations

from typing import Any

from app.agent.retrieval.keywords import extract_keywords
from app.agent.retrieval.search import global_search, local_search, naive_search
from app.agent.retrieval.chunk_picker import (
    collect_chunks_from_entities,
    pick_by_weighted_polling,
)
from app.agent.retrieval.context_builder import build_context
from app.agent.tools.base import BaseTool
from app.agent.storage_manager import StorageManager


class SearchTool(BaseTool):
    """GraphRAG 检索：关键词提取 → 三路搜索 → 选块 → 构建上下文。"""

    name = "search"
    description = "从知识库中检索相关信息并构建结构化上下文"

    def run(
        self,
        query: str,
        storage_manager: StorageManager | None = None,
    ) -> dict[str, Any]:
        if not storage_manager or not storage_manager.has_documents:
            return {
                "context": "（当前没有已摄入的文档，无法检索知识库。）",
                "has_documents": False,
                "entities": [],
                "relations": [],
            }

        # 关键词提取
        keywords = extract_keywords(query)
        ll_keywords = keywords.get("ll_keywords", [])
        hl_keywords = keywords.get("hl_keywords", [])

        storage_ctx = storage_manager.get_context()

        # 三路搜索
        local_result = local_search(ll_keywords, storage_ctx["entities_vdb"])
        global_result = global_search(hl_keywords, storage_ctx["relationships_vdb"])
        vector_chunks = naive_search(query, storage_ctx["chunks_vdb"])

        # 合并实体和关系
        all_entities = local_result.get("entities", []) + global_result.get("entities", [])
        all_relations = local_result.get("relations", []) + global_result.get("relations", [])

        # 实体去重
        seen_ids = set()
        dedup_entities = []
        for e in all_entities:
            eid = e.get("id", "")
            if eid not in seen_ids:
                seen_ids.add(eid)
                dedup_entities.append(e)

        # 关系去重
        seen_rels = set()
        dedup_relations = []
        for r in all_relations:
            rm = r.get("metadata", {})
            key = (rm.get("source", ""), rm.get("target", ""), rm.get("type", ""))
            if key not in seen_rels:
                seen_rels.add(key)
                dedup_relations.append(r)

        # 加权选块
        entity_chunks = collect_chunks_from_entities(dedup_entities, storage_ctx["text_chunks_kv"])
        picked_chunks = pick_by_weighted_polling(
            entity_chunks=entity_chunks,
            relation_chunks=[],
            vector_chunks=vector_chunks,
        )

        # 构建上下文
        context, raw_data = build_context(
            query=query,
            entities=dedup_entities,
            relations=dedup_relations,
            vector_chunks=picked_chunks,
            text_chunks_store=storage_ctx["text_chunks_kv"],
        )

        return {
            "context": context,
            "has_documents": True,
            "entities": dedup_entities,
            "relations": dedup_relations,
            "raw_data": raw_data,
        }
