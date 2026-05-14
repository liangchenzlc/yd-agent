from __future__ import annotations

from typing import Any

from app.agent.retrieval.chunk_picker import (
    collect_chunks_from_entities,
    select_weighted_chunks,
)
from app.agent.retrieval.context_builder import build_context
from app.agent.retrieval.keywords import extract_keywords
from app.agent.retrieval.reranker import rerank
from app.agent.retrieval.search import global_search, local_search, search_by_vector
from app.agent.storage_manager import StorageManager
from app.agent.tools.base import BaseTool, as_tool


class SearchTool(BaseTool):
    """知识库检索工具集，支持 GraphRAG 三路检索。"""

    name = "search"
    description = "知识库检索工具集，支持 GraphRAG 多跳推理检索"

    def __init__(self, storage_manager: StorageManager | None = None):
        self.storage_manager = storage_manager

    def set_storage_manager(self, storage_manager: StorageManager | None):
        """注入 storage_manager 并清除缓存，供 retrieval_worker 在请求时调用。"""
        self.storage_manager = storage_manager
        if hasattr(self, "_lc_tools_cache"):
            del self._lc_tools_cache

    @as_tool(
        name="search_knowledge_base",
        description=(
            "从知识库中检索与问题相关的信息。支持 GraphRAG 多跳推理，"
            "可以回答需要跨文档联合查询的问题。"
            "query 是用户的自然语言问题。"
        ),
    )
    def search(self, query: str) -> str:
        if not self.storage_manager or not self.storage_manager.has_documents:
            return "（当前没有已摄入的文档，无法检索知识库。）"

        # 关键词提取
        keywords = extract_keywords(query)
        ll_keywords = keywords.get("ll_keywords", [])
        hl_keywords = keywords.get("hl_keywords", [])

        storage_ctx = self.storage_manager.get_context()

        # 三路搜索
        local_result = local_search(ll_keywords, storage_ctx["entities_vdb"])
        global_result = global_search(hl_keywords, storage_ctx["relationships_vdb"])
        vector_chunks = search_by_vector(query, storage_ctx["chunks_vdb"])

        # 合并实体和关系（去重）
        all_entities = local_result.get("entities", []) + global_result.get("entities", [])
        all_relations = local_result.get("relations", []) + global_result.get("relations", [])

        seen_ids = set()
        dedup_entities = []
        for e in all_entities:
            eid = e.get("id", "")
            if eid not in seen_ids:
                seen_ids.add(eid)
                dedup_entities.append(e)

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
        picked_chunks = select_weighted_chunks(
            entity_chunks=entity_chunks,
            relation_chunks=[],
            vector_chunks=vector_chunks,
        )

        # 重排序：用 rerank 模型对候选块二阶段精排
        picked_chunks = rerank(query, picked_chunks, top_k=5)

        # 构建上下文
        context, _ = build_context(
            query=query,
            entities=dedup_entities,
            relations=dedup_relations,
            vector_chunks=picked_chunks,
            text_chunks_store=storage_ctx["text_chunks_kv"],
        )

        return context or "未找到与问题相关的信息。"
