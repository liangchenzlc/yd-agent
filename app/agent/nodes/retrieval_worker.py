from app.agent.constants import WORKER_RETRIEVAL
from app.agent.llm import factory as llm_factory
from app.agent.prompts import RETRIEVAL_WORKER_PROMPT
from app.agent.retrieval.chunk_picker import pick_by_weighted_polling
from app.agent.retrieval.context_builder import build_context
from app.agent.retrieval.keywords import extract_keywords
from app.agent.retrieval.search import global_search, local_search, naive_search
from app.agent.state import AgentState
from app.agent.storage_manager import StorageManager


def retrieval_worker_node(state: AgentState, storage_manager: StorageManager | None = None) -> dict:
    """检索 Worker：使用 GraphRAG 执行知识检索。

    如果未摄入文档（VDB 为空），回退到 LLM-only 模式。
    """
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    feedback = state.get("refinement_feedback", "")
    refinement_context = f"## 上一轮反馈\n{feedback}\n请根据反馈改进检索。" if feedback else ""

    # 判断是否有文档可检索
    if storage_manager and storage_manager.has_documents:
        # 关键词提取
        keywords = extract_keywords(user_message)
        ll_keywords = keywords.get("ll_keywords", [])
        hl_keywords = keywords.get("hl_keywords", [])

        storage_ctx = storage_manager.get_context()
        entities_vdb = storage_ctx["entities_vdb"]
        relationships_vdb = storage_ctx["relationships_vdb"]
        chunks_vdb = storage_ctx["chunks_vdb"]
        text_chunks_kv = storage_ctx["text_chunks_kv"]

        # 三路并行搜索
        local_result = local_search(ll_keywords, entities_vdb)
        global_result = global_search(hl_keywords, relationships_vdb)
        vector_chunks = naive_search(user_message, chunks_vdb)

        # 合并实体和关系
        all_entities = local_result.get("entities", []) + global_result.get("entities", [])
        all_relations = local_result.get("relations", []) + global_result.get("relations", [])

        # 去重（按 id）
        seen_entity_ids = set()
        deduped_entities = []
        for e in all_entities:
            eid = e.get("id", "")
            if eid not in seen_entity_ids:
                seen_entity_ids.add(eid)
                deduped_entities.append(e)

        seen_rel_keys = set()
        deduped_relations = []
        for r in all_relations:
            rmeta = r.get("metadata", {})
            key = (rmeta.get("source", ""), rmeta.get("target", ""), rmeta.get("type", ""))
            if key not in seen_rel_keys:
                seen_rel_keys.add(key)
                deduped_relations.append(r)

        # 加权轮询选择 chunk
        picked_chunks = pick_by_weighted_polling(
            entity_chunks=collect_chunks(deduped_entities, text_chunks_kv),
            relation_chunks=[],
            vector_chunks=vector_chunks,
        )

        # 构建上下文
        graphrag_context, raw_data = build_context(
            query=user_message,
            entities=deduped_entities,
            relations=deduped_relations,
            vector_chunks=picked_chunks,
            text_chunks_store=text_chunks_kv,
        )
    else:
        # 回退：无文档，使用 LLM-only
        graphrag_context = "（当前没有已摄入的文档，无法检索知识库。）"
        raw_data = {"fallback": True}

    llm = llm_factory.create_llm()
    prompt = (
        RETRIEVAL_WORKER_PROMPT.replace("{refinement_context}", refinement_context)
        .replace("{graphrag_context}", graphrag_context)
        .replace("{user_message}", user_message)
    )
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)

    return {
        "worker_results": [
            {
                "worker": WORKER_RETRIEVAL,
                "content": content,
                "error": None,
                "metadata": {"has_documents": bool(storage_manager and storage_manager.has_documents), **raw_data},
            }
        ]
    }


def collect_chunks(entities: list[dict], text_chunks_kv) -> list[dict]:
    """从实体元数据中收集关联的文本块。"""
    chunks = []
    for e in entities:
        meta = e.get("metadata", {})
        doc_id = meta.get("doc_id", "")
        if doc_id:
            # 尝试从 KV 获取文档元数据
            pass
    return chunks
