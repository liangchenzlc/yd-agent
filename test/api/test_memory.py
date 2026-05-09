"""记忆系统测试：MemoryManager, 提取器, 检索器, API 端点（真实 LLM + Embedding）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


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
        import asyncio
        profile = asyncio.run(mem_mgr.get_user_profile("new_user"))
        assert profile["user_id"] == "new_user"
        assert profile["topics"] == {}
        assert profile["total_interactions"] == 0
        assert profile["recent_history"] == []

    def test_update_profile(self, mem_mgr):
        import asyncio
        asyncio.run(mem_mgr.update_user_profile(
            "user1", message="你好", answer="你好！有什么可以帮助你的？"
        ))
        profile = asyncio.run(mem_mgr.get_user_profile("user1"))
        assert profile["total_interactions"] == 1
        assert len(profile["recent_history"]) == 1
        assert profile["last_active"] is not None

    def test_update_profile_with_topics(self, mem_mgr):
        import asyncio
        asyncio.run(mem_mgr.update_user_profile(
            "user1", message="Python 怎么学？", answer="...", topics=["Python", "编程"]
        ))
        profile = asyncio.run(mem_mgr.get_user_profile("user1"))
        assert profile["topics"]["Python"] == 1
        assert profile["topics"]["编程"] == 1

    def test_store_and_retrieve_memory(self, mem_mgr):
        """用真实 Embedding 存储记忆后检索。"""
        import asyncio
        from app.agent.llm.factory import create_embeddings

        embeddings_api = create_embeddings()
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
        assert isinstance(results, list)

    def test_retrieve_wrong_user(self, mem_mgr):
        """用户 A 不应检索到用户 B 的记忆。"""
        import asyncio
        from app.agent.llm.factory import create_embeddings

        embeddings_api = create_embeddings()
        memories = [{"type": "fact", "content": "用户 A 喜欢 Python 编程", "importance": 0.9}]

        asyncio.run(mem_mgr.store_session_memory(
            "user_a", "session_1", memories, embeddings_api, importance_threshold=0.3
        ))

        results = asyncio.run(mem_mgr.get_relevant_memories(
            "user_b", "Python 编程", embeddings_api, k=5
        ))
        assert len(results) == 0

    def test_session_history(self, mem_mgr):
        import asyncio
        for i in range(3):
            asyncio.run(mem_mgr.update_user_profile(
                "user1", message=f"消息{i}", answer=f"回答{i}"
            ))

        history = asyncio.run(mem_mgr.get_session_history("user1", limit=2))
        assert len(history) == 2
        assert history[-1]["message"] == "消息2"

    def test_prune_expired_working_memory(self, mem_mgr):
        """过期的工作记忆应被剪枝。"""
        import asyncio
        from datetime import datetime, timedelta, timezone
        from app.agent.llm.factory import create_embeddings

        embeddings_api = create_embeddings()
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

        mem_id = "user1_test_old_mem"
        text = "过期记忆"
        embs = embeddings_api.embed_documents([text])
        mem_mgr.working_memory_vdb.add_texts(
            [mem_id], [text], [embs[0]],
            [{"type": "fact", "importance": 0.5, "user_id": "user1", "timestamp": old_ts}]
        )

        asyncio.run(mem_mgr.prune_expired_memories())
        assert mem_id not in mem_mgr.working_memory_vdb._id_to_meta

    def test_forget_user(self, mem_mgr):
        """遗忘用户应删除所有记忆和画像。"""
        import asyncio
        from app.agent.llm.factory import create_embeddings

        embeddings_api = create_embeddings()
        asyncio.run(mem_mgr.update_user_profile("user1", "hello", "hi"))
        asyncio.run(mem_mgr.store_session_memory(
            "user1", "s1", [{"type": "fact", "content": "test", "importance": 0.9}],
            embeddings_api
        ))

        asyncio.run(mem_mgr.forget_user("user1"))

        profile = asyncio.run(mem_mgr.get_user_profile("user1"))
        assert profile["total_interactions"] == 0
        assert profile["recent_history"] == []


class TestExtractor:
    """测试记忆提取功能（真实 LLM）。"""

    def test_extract_memories_format(self):
        """用真实 LLM 提取记忆，验证返回格式。"""
        from app.agent.memory.extractor import extract_memories_from_conversation
        memories = extract_memories_from_conversation("我是 Python 后端工程师", "好的，已记住你的角色。")
        assert isinstance(memories, list)


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


class TestMemoryAPI:
    """测试记忆管理 REST API（真实依赖）。"""

    @pytest.fixture
    def client(self):
        from app.api.routes import chat
        chat._agent_graph = None
        with TestClient(app) as c:
            yield c

    def test_get_memories_empty(self, client):
        resp = client.get("/memory/user_new")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user_new"
        assert data["core_memories"] == []
        assert data["working_memories"] == []

    def test_get_profile_default(self, client):
        resp = client.get("/profile/user_new")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user_new"
        assert data["total_interactions"] == 0

    def test_delete_memories(self, client):
        resp = client.delete("/memory/user_to_delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["user_id"] == "user_to_delete"


class TestChatMemoryIntegration:
    """测试 Chat 端点与记忆系统的集成（真实 LLM）。"""

    @pytest.fixture
    def client(self):
        from app.api.routes import chat
        chat._agent_graph = None
        with TestClient(app) as c:
            yield c

    def test_chat_with_user_id(self, client):
        resp = client.post("/chat", json={
            "message": "你好",
            "user_id": "test_user_1",
        }, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "memories_updated" in data
        assert "answer" in data

    def test_chat_stores_memory(self, client):
        client.post("/chat", json={
            "message": "我是 Python 后端工程师",
            "user_id": "test_user_2",
        }, timeout=60)
        client.post("/chat", json={
            "message": "帮我写一个排序函数",
            "user_id": "test_user_2",
        }, timeout=60)

        resp = client.get("/profile/test_user_2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_interactions"] >= 1


class TestMemoryConfigFallback:
    """测试记忆功能禁用或管理器为空时的回退行为。"""

    def test_load_memory_without_manager(self):
        from app.agent.nodes.load_memory import load_memory_node
        from test.helpers import make_initial_state

        state = make_initial_state("你好")
        result = load_memory_node(state, memory_manager=None)
        assert result["user_profile"] == {}
        assert result["relevant_memories"] == []
        assert result["session_history"] == []

    def test_save_memory_without_manager(self):
        from app.agent.nodes.save_memory import save_memory_node
        from test.helpers import make_initial_state

        state = make_initial_state("你好")
        result = save_memory_node(state, memory_manager=None)
        assert result["memories_updated"] is False
