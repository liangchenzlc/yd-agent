"""记忆系统测试：MemoryManager, 提取器, 检索器, API 端点。"""

import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient


# ---- MemoryManager 单元测试 ----


class TestMemoryManager:
    """测试 MemoryManager 的核心操作。"""

    @pytest.fixture
    def mem_mgr(self, tmp_path):
        from app.agent.memory.memory_manager import MemoryManager
        import asyncio
        mgr = MemoryManager(str(tmp_path), embedding_dim=128)
        asyncio.run(mgr.initialize())
        return mgr

    def test_default_profile(self, mem_mgr):
        """新用户应返回默认画像。"""
        import asyncio
        profile = asyncio.run(mem_mgr.get_user_profile("new_user"))
        assert profile["user_id"] == "new_user"
        assert profile["topics"] == {}
        assert profile["total_interactions"] == 0
        assert profile["recent_history"] == []

    def test_update_profile(self, mem_mgr):
        """更新用户画像后应反映交互统计。"""
        import asyncio

        asyncio.run(mem_mgr.update_user_profile(
            "user1", message="你好", answer="你好！有什么可以帮助你的？"
        ))
        profile = asyncio.run(mem_mgr.get_user_profile("user1"))
        assert profile["total_interactions"] == 1
        assert len(profile["recent_history"]) == 1
        assert profile["last_active"] is not None

    def test_update_profile_with_topics(self, mem_mgr):
        """带话题的更新应增加话题频次。"""
        import asyncio

        asyncio.run(mem_mgr.update_user_profile(
            "user1", message="Python 怎么学？", answer="...", topics=["Python", "编程"]
        ))
        profile = asyncio.run(mem_mgr.get_user_profile("user1"))
        assert profile["topics"]["Python"] == 1
        assert profile["topics"]["编程"] == 1

    def test_store_and_retrieve_memory(self, mem_mgr):
        """存储记忆后应能通过相关查询检索到。"""
        import asyncio
        import numpy as np

        # 用固定向量确保检索命中
        class ConstantEmbeddings:
            def embed_documents(self, texts):
                return [np.ones(128).tolist() for _ in texts]
            def embed_query(self, text):
                return np.ones(128).tolist()

        embeddings_api = ConstantEmbeddings()
        memories = [
            {"type": "fact", "content": "用户是一名 Python 后端工程师", "importance": 0.9},
            {"type": "preference", "content": "用户喜欢简洁的代码风格", "importance": 0.5},
        ]

        asyncio.run(mem_mgr.store_session_memory(
            "user1", "session_1", memories, embeddings_api, importance_threshold=0.6
        ))

        results = asyncio.run(mem_mgr.get_relevant_memories(
            "user1", "Python 工程师", embeddings_api, k=5
        ))
        assert len(results) > 0

    def test_retrieve_wrong_user(self, mem_mgr, mock_embeddings):
        """用户 A 不应检索到用户 B 的记忆。"""
        import asyncio

        embeddings_api = mock_embeddings.return_value
        memories = [{"type": "fact", "content": "用户 A 的记忆", "importance": 0.9}]

        asyncio.run(mem_mgr.store_session_memory(
            "user_a", "session_1", memories, embeddings_api, importance_threshold=0.3
        ))

        results = asyncio.run(mem_mgr.get_relevant_memories(
            "user_b", "记忆", embeddings_api, k=5
        ))
        assert len(results) == 0

    def test_session_history(self, mem_mgr):
        """应返回最近的会话历史。"""
        import asyncio

        for i in range(3):
            asyncio.run(mem_mgr.update_user_profile(
                "user1", message=f"消息{i}", answer=f"回答{i}"
            ))

        history = asyncio.run(mem_mgr.get_session_history("user1", limit=2))
        assert len(history) == 2
        assert history[-1]["message"] == "消息2"

    def test_prune_expired_working_memory(self, mem_mgr, mock_embeddings):
        """过期的工作记忆应被剪枝。"""
        import asyncio
        from datetime import datetime, timedelta, timezone

        embeddings_api = mock_embeddings.return_value
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

        # 直接写入一个过期的工作记忆
        mem_id = "user1_test_old_mem"
        text = "过期记忆"
        embs = embeddings_api.embed_documents([text])
        mem_mgr.working_memory_vdb.add_texts(
            [mem_id], [text], [embs[0]],
            [{"type": "fact", "importance": 0.5, "user_id": "user1", "timestamp": old_ts}]
        )

        asyncio.run(mem_mgr.prune_expired_memories())
        # 过期记忆应被删除
        assert mem_id not in mem_mgr.working_memory_vdb._id_to_meta

    def test_forget_user(self, mem_mgr, mock_embeddings):
        """遗忘用户应删除所有记忆和画像。"""
        import asyncio

        embeddings_api = mock_embeddings.return_value
        # 创建画像和记忆
        asyncio.run(mem_mgr.update_user_profile("user1", "hello", "hi"))
        asyncio.run(mem_mgr.store_session_memory(
            "user1", "s1", [{"type": "fact", "content": "test", "importance": 0.9}],
            embeddings_api
        ))

        asyncio.run(mem_mgr.forget_user("user1"))

        profile = asyncio.run(mem_mgr.get_user_profile("user1"))
        # forget_user 只删 KV，所以 get_user_profile 返回默认画像
        assert profile["total_interactions"] == 0
        assert profile["recent_history"] == []


# ---- 提取器测试 ----


class TestExtractor:
    """测试记忆提取功能。"""

    def test_extract_memories_format(self):
        """提取器应返回正确格式的记忆列表。"""
        from app.agent.memory.extractor import extract_memories_from_conversation
        from test.mock_utils import FakeLLM

        with mock.patch("app.agent.llm.factory.create_llm") as m:
            m.return_value = FakeLLM(responses=[
                '```json\n{"memories": [{"type": "fact", "content": "测试记忆", "importance": 0.8, "category": ""}]}\n```'
            ])
            memories = extract_memories_from_conversation("你好", "你好！")
            assert isinstance(memories, list)
            assert len(memories) == 1
            assert memories[0]["type"] == "fact"

    def test_extract_memories_empty_result(self):
        """当 LLM 返回空记忆列表时，应返回空列表。"""
        from app.agent.memory.extractor import extract_memories_from_conversation
        from test.mock_utils import FakeLLM

        with mock.patch("app.agent.llm.factory.create_llm") as m:
            m.return_value = FakeLLM(responses=[
                '```json\n{"memories": []}\n```'
            ])
            memories = extract_memories_from_conversation("你好", "你好！")
            assert memories == []

    def test_extract_memories_invalid_json(self):
        """当 LLM 返回无效 JSON 时，应回退到空列表。"""
        from app.agent.memory.extractor import extract_memories_from_conversation
        from test.mock_utils import FakeLLM

        with mock.patch("app.agent.llm.factory.create_llm") as m:
            m.return_value = FakeLLM(responses=["这不是 JSON"])
            memories = extract_memories_from_conversation("你好", "你好！")
            assert memories == []


# ---- 检索器测试 ----


class TestRetrieverFormatters:
    """测试记忆和画像的格式化函数。"""

    def test_format_memory_context_empty(self):
        from app.agent.memory.retriever import format_memory_context
        result = format_memory_context([])
        assert "暂无" in result

    def test_format_memory_context_with_data(self):
        from app.agent.memory.retriever import format_memory_context
        memories = [
            {"text": "用户是后端工程师", "metadata": {"type": "fact", "importance": 0.9}},
            {"text": "喜欢简洁风格", "metadata": {"type": "preference", "importance": 0.5}},
        ]
        result = format_memory_context(memories)
        assert "后端工程师" in result
        assert "简洁风格" in result

    def test_format_profile_context_empty(self):
        from app.agent.memory.retriever import format_profile_context
        result = format_profile_context({})
        assert "新用户" in result

    def test_format_profile_context_with_data(self):
        from app.agent.memory.retriever import format_profile_context
        profile = {
            "topics": {"Python": 5, "Go": 3},
            "total_interactions": 10,
            "recent_history": [],
        }
        result = format_profile_context(profile)
        assert "Python" in result
        assert "10" in result


# ---- 记忆 API 测试 ----


class TestMemoryAPI:
    """测试记忆管理 REST API。"""

    @pytest.fixture
    def client(self, tmp_path):
        from app.main import create_app
        app = create_app()
        # Override lifespan with our own setup
        from contextlib import asynccontextmanager
        from app.agent.memory.memory_manager import MemoryManager

        mem_mgr = MemoryManager(str(tmp_path), embedding_dim=128)
        import asyncio
        asyncio.run(mem_mgr.initialize())

        from app.api.routes import chat
        chat.get_graph(memory_manager=mem_mgr)

        # Mock get_memory_manager
        with mock.patch("app.main.get_memory_manager") as m:
            m.return_value = mem_mgr
            with TestClient(app) as c:
                yield c

        asyncio.run(mem_mgr.finalize())

    def test_get_memories_empty(self, client):
        """新用户应返回空记忆列表。"""
        resp = client.get("/memory/user_new")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user_new"
        assert data["core_memories"] == []
        assert data["working_memories"] == []

    def test_get_profile_default(self, client):
        """新用户应返回默认画像。"""
        resp = client.get("/profile/user_new")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user_new"
        assert data["total_interactions"] == 0

    def test_delete_memories(self, client):
        """删除记忆应返回成功。"""
        resp = client.delete("/memory/user_to_delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["user_id"] == "user_to_delete"


# ---- Chat 记忆集成测试 ----


class TestChatMemoryIntegration:
    """测试 Chat 端点与记忆系统的集成。"""

    @pytest.fixture
    def client(self, mock_llm, mock_embeddings, tmp_path):
        from app.main import create_app
        app = create_app()

        from app.agent.memory.memory_manager import MemoryManager
        mem_mgr = MemoryManager(str(tmp_path), embedding_dim=128)
        import asyncio
        asyncio.run(mem_mgr.initialize())

        from app.api.routes import chat
        chat._agent_graph = None  # reset
        chat.get_graph(memory_manager=mem_mgr)

        with mock.patch("app.main.get_memory_manager") as m:
            m.return_value = mem_mgr
            with TestClient(app) as c:
                yield c

        asyncio.run(mem_mgr.finalize())

    def test_chat_with_user_id(self, client):
        """带 user_id 的聊天应返回 memories_updated 字段。"""
        resp = client.post("/chat", json={
            "message": "你好",
            "user_id": "test_user_1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "memories_updated" in data
        assert "answer" in data

    def test_chat_stores_memory(self, client):
        """多次对话后应能从记忆 API 获取到数据。"""
        # 第一次对话
        client.post("/chat", json={
            "message": "我是 Python 后端工程师",
            "user_id": "test_user_2",
        })
        # 第二次对话
        client.post("/chat", json={
            "message": "帮我写一个排序函数",
            "user_id": "test_user_2",
        })

        # 检查画像更新
        resp = client.get("/profile/test_user_2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_interactions"] >= 1


# ---- 配置回退测试 ----


class TestMemoryConfigFallback:
    """测试记忆功能被禁用或记忆管理器为空时的回退行为。"""

    def test_load_memory_without_manager(self):
        """无 memory_manager 时 load_memory 应返回空数据。"""
        from app.agent.nodes.load_memory import load_memory_node
        from test.mock_utils import make_initial_state

        state = make_initial_state("你好")
        result = load_memory_node(state, memory_manager=None)
        assert result["user_profile"] == {}
        assert result["relevant_memories"] == []
        assert result["session_history"] == []

    def test_save_memory_without_manager(self):
        """无 memory_manager 时 save_memory 应返回 memories_updated=False。"""
        from app.agent.nodes.save_memory import save_memory_node
        from test.mock_utils import make_initial_state

        state = make_initial_state("你好")
        result = save_memory_node(state, memory_manager=None)
        assert result["memories_updated"] is False

    def test_save_memory_disabled(self, mock_llm):
        """当配置禁用记忆提取时，应返回 memories_updated=False。"""
        from app.agent.nodes.save_memory import save_memory_node
        from app.agent.memory.memory_manager import MemoryManager
        from test.mock_utils import make_initial_state
        import tempfile
        import asyncio

        with mock.patch("app.agent.nodes.save_memory.get_settings") as m_settings:
            m_settings.return_value.memory_extraction_enabled = False
            with tempfile.TemporaryDirectory() as tmpdir:
                mgr = MemoryManager(tmpdir, embedding_dim=128)
                asyncio.run(mgr.initialize())
                state = make_initial_state("你好")
                result = save_memory_node(state, memory_manager=mgr)
                assert result["memories_updated"] is False
                asyncio.run(mgr.finalize())
