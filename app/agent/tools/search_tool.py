from __future__ import annotations

import concurrent.futures
from typing import Any

from app.agent.constants import MAX_CONTEXT_TOKENS
from app.agent.retrieval.chunk_picker import reciprocal_rank_fusion
from app.agent.retrieval.context_builder import build_context, expand_neighbor_chunks
from app.agent.retrieval.reranker import rerank
from app.agent.retrieval.search import search_by_bm25, vector_search
from app.agent.storage_manager import StorageManager
from app.agent.tools.base import BaseTool, as_tool


def _apply_metadata_filters(
    chunks: list[dict[str, Any]],
    filters: dict | None,
) -> list[dict[str, Any]]:
    """后过滤：保留 metadata 中所有 filter key=value 匹配的 chunk。

    在 rerank 前执行以保留更多候选（过滤后再 rerank）。
    注意这是精确匹配，不支持范围/模糊查询。如需复杂过滤应扩展此函数。
    """
    if not filters:
        return chunks
    result = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        if all(meta.get(k) == v for k, v in filters.items()):
            result.append(chunk)
    return result


class SearchTool(BaseTool):
    """知识库检索工具集，支持混合检索（向量 + BM25 + Rerank）。

    注意：storage_manager 不在 __init__ 中注入，而是在 retrieval_worker 每次请求时
    通过 set_storage_manager() 注入。这是因为 ToolRegistry.init_defaults() 在应用启动时
    创建 SearchTool 实例，此时 storage_manager 尚未初始化。每次注入后清除缓存确保
    工具描述中使用的存储上下文是最新的。
    """

    name = "search"
    description = "知识库检索工具集，支持混合检索（向量 + 关键词 + 重排序）"

    def __init__(self, storage_manager: StorageManager | None = None):
        self.storage_manager = storage_manager

    def set_storage_manager(self, storage_manager: StorageManager | None):
        """请求时注入 storage_manager 并清除 LangChain 工具缓存。

        每次注入后清除 _lc_tools_cache 使得下次 get_lc_tools() 重新创建工具实例。
        虽然当前工具方法不依赖 storage_manager 生成 schema，但这种设计保持了
        未来扩展的可能性（如动态工具描述）。
        """
        self.storage_manager = storage_manager
        if hasattr(self, "_lc_tools_cache"):
            del self._lc_tools_cache

    @as_tool(
        name="search_knowledge_base",
        description=(
            "从知识库中检索与问题相关的信息。支持混合检索（向量+关键词），"
            "自动融合多路结果并重排序。"
            "query 是用户的自然语言问题。"
            "filters 是可选的元数据过滤条件，格式如 {\"file_type\": \"pdf\"}。"
        ),
    )
    def search(self, query: str, filters: str | None = None) -> str:
        """检索知识库。

        检索管线（性能优化后）：
        1. 向量 + BM25 双路并行检索（ThreadPoolExecutor）
        2. RRF 融合两路结果
        3. 元数据后过滤
        4. 结果少时（≤5 条）跳过 Rerank API 调用，按 score 排序
        5. 邻近块补全（补充分片丢失的上下文）
        6. Token 感知截断构建上下文
        """
        if not self.storage_manager or not self.storage_manager.has_documents:
            return "（当前没有已摄入的文档，无法检索知识库。）"

        # 解析 filters JSON 字符串参数
        parsed_filters: dict | None = None
        if filters:
            import json
            try:
                parsed_filters = json.loads(filters)
                if not isinstance(parsed_filters, dict):
                    parsed_filters = None
            except (json.JSONDecodeError, TypeError):
                pass

        # 直接使用原始 query 做 BM25，跳过 LLM 关键词提取（P0 性能优化）
        bm25_query = query

        storage_ctx = self.storage_manager.get_context()

        # 双路并行检索（P1 优化）：向量 + BM25 互不依赖
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fut_v = pool.submit(vector_search, query, storage_ctx["chunks_vdb"], 20)
            fut_b = pool.submit(search_by_bm25, bm25_query, storage_ctx["bm25_store"], 20)
            vector_results = fut_v.result()
            bm25_results = fut_b.result()

        # RRF 融合
        fused_chunks = reciprocal_rank_fusion(vector_results, bm25_results, top_k=20)

        # 元数据后过滤（rerank 前，保留更多候选）
        fused_chunks = _apply_metadata_filters(fused_chunks, parsed_filters)

        # 重排序：候选 ≤5 时跳过 API 调用（P1 优化），直接按 score 排序
        rerank_top_k = 5
        if len(fused_chunks) <= rerank_top_k:
            fused_chunks.sort(key=lambda d: d.get("score", 0), reverse=True)
            reranked_chunks = fused_chunks[:rerank_top_k]
        else:
            reranked_chunks = rerank(query, fused_chunks, top_k=rerank_top_k)

        # 邻近块补全
        reranked_chunks = expand_neighbor_chunks(
            reranked_chunks, storage_ctx["text_chunks_kv"]
        )

        # Token 感知构建上下文
        context, _ = build_context(
            query=query,
            chunks=reranked_chunks,
            max_tokens=MAX_CONTEXT_TOKENS,
        )

        return context or "未找到与问题相关的信息。"
