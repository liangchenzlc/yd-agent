"""测试 GraphRAG 检索：关键词提取、搜索、上下文构建。"""

from unittest import mock

import pytest

from app.agent.ingestion.chunker import chunk_text
from app.agent.retrieval.keywords import extract_keywords
from app.agent.retrieval.context_builder import build_context
from app.agent.storage.vector_store import FAISSStore
from app.agent.storage.kv_store import JsonKVStore

SAMPLE_TEXT = """
人工智能（AI）是计算机科学的一个分支，致力于创建能够模拟人类智能的系统。
机器学习（ML）是 AI 的一个子集，使系统能够从数据中学习。
深度学习（DL）是机器学习的一个分支，使用多层神经网络。
自然语言处理（NLP）是 AI 的另一个重要分支。

在 yd-Agent 项目中，我们使用 LangGraph 构建多智能体系统。
Supervisor 负责分析用户意图并分发任务给不同的 Worker。
Retrieval Worker 负责知识检索，Code Worker 负责代码执行。
"""


class TestChunker:
    def test_chunk_text_basic(self):
        chunks = chunk_text(SAMPLE_TEXT, chunk_size=500, chunk_overlap=50)
        assert len(chunks) >= 1
        assert all("chunk_id" in c for c in chunks)
        assert all("content" in c for c in chunks)
        assert all("index" in c for c in chunks)

    def test_chunk_text_empty(self):
        chunks = chunk_text("")
        assert chunks == []

    def test_chunk_text_short(self):
        chunks = chunk_text("短文本。", chunk_size=1200)
        assert len(chunks) == 1
        assert chunks[0]["content"] == "短文本。"


class TestKeywordExtraction:
    def test_extract_keywords(self, mock_llm):
        result = extract_keywords("LangGraph 中的 Supervisor 是如何工作的？")
        assert isinstance(result, dict)
        assert "ll_keywords" in result
        assert "hl_keywords" in result

    def test_extract_keywords_empty(self, mock_llm):
        result = extract_keywords("")
        assert isinstance(result, dict)


class TestContextBuilder:
    def test_build_context_with_data(self):
        kv = JsonKVStore("test", "/tmp")
        context_str, raw = build_context(
            query="AI是什么",
            entities=[{"id": "AI", "text": "人工智能", "metadata": {"type": "concept"}}],
            relations=[{"metadata": {"source": "AI", "target": "ML", "type": "subset_of"}}],
            vector_chunks=[{"text": "人工智能是计算机科学的分支。"}],
            text_chunks_store=kv,
        )
        assert "人工智能" in context_str
        assert raw["entity_count"] == 1
        assert raw["relation_count"] == 1
        assert raw["chunk_count"] == 1

    def test_build_context_empty(self):
        kv = JsonKVStore("test", "/tmp")
        context_str, raw = build_context("test", [], [], [], kv)
        assert context_str == ""
        assert raw["entity_count"] == 0


class TestFAISSStore:
    def test_is_empty_initially(self):
        store = FAISSStore("test", "/tmp", embedding_dim=128)
        assert store.is_empty() is True

    def test_add_and_search(self):
        import numpy as np

        store = FAISSStore("test", "/tmp", embedding_dim=128)
        # 添加一个随机向量
        emb = np.random.randn(128).tolist()
        store.add_texts(["id1"], ["测试文本"], [emb])
        assert not store.is_empty()

        result = store.similarity_search_by_vector(emb, k=5, score_threshold=0.0)
        assert len(result) > 0
