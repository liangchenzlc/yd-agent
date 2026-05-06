"""评估系统测试：EvalManager, 评估器, 反馈 API, 集成测试。"""

import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient


# ---- EvalManager 单元测试 ----


class TestEvalManager:
    """测试 EvalManager 的核心 CRUD 和统计操作。"""

    @pytest.fixture
    def eval_mgr(self, tmp_path):
        from app.agent.eval.eval_manager import EvalManager
        import asyncio
        mgr = EvalManager(str(tmp_path))
        asyncio.run(mgr.initialize())
        return mgr

    def test_default_stats(self, eval_mgr):
        """初始状态应返回全零统计。"""
        import asyncio
        summary = asyncio.run(eval_mgr.get_eval_summary())
        assert summary["total_eval_runs"] == 0
        assert summary["avg_score"] == 0.0
        assert summary["pass_rate"] == 0.0
        assert summary["total_hard_cases"] == 0

    def test_add_and_get_eval_run(self, eval_mgr):
        """添加评估记录后应能检索到。"""
        import asyncio
        run_data = {
            "user_id": "user1",
            "session_id": "s1",
            "message": "hello",
            "answer": "hi",
            "overall_score": 8,
            "worker_results": [],
            "refinements": 0,
            "dimensions": [],
            "is_hard_case": False,
            "timestamp": "2026-05-01T00:00:00+00:00",
        }
        run_id = asyncio.run(eval_mgr.add_eval_run(run_data))
        assert run_id

        run = asyncio.run(eval_mgr.get_eval_run(run_id))
        assert run is not None
        assert run["overall_score"] == 8
        assert run["user_id"] == "user1"

    def test_list_eval_runs_with_filters(self, eval_mgr):
        """列表查询应支持分页和分数过滤。"""
        import asyncio
        for i in range(5):
            asyncio.run(eval_mgr.add_eval_run({
                "user_id": "u1", "overall_score": i + 1,
                "timestamp": f"2026-05-0{i+1}T00:00:00+00:00",
            }))
        runs = asyncio.run(eval_mgr.list_eval_runs(limit=3, offset=0))
        assert len(runs) == 3
        # 应按时间倒序
        assert runs[0]["overall_score"] == 5

        # 分数过滤：scores=[1,2,3,4,5], min=4,max=6 → [4,5]
        runs = asyncio.run(eval_mgr.list_eval_runs(limit=10, min_score=4, max_score=6))
        assert len(runs) == 2

    def test_stats_update(self, eval_mgr):
        """更新统计应正确累计分值和分桶。"""
        import asyncio
        asyncio.run(eval_mgr.update_stats(8))
        asyncio.run(eval_mgr.update_stats(3))
        asyncio.run(eval_mgr.update_stats(9))

        summary = asyncio.run(eval_mgr.get_eval_summary())
        assert summary["total_eval_runs"] == 3
        assert summary["avg_score"] == round((8 + 3 + 9) / 3, 2)
        # 3->0-3 bucket, 8->7-8 bucket, 9->9-10 bucket
        dist = summary["score_distribution"]
        assert dist["0-3"] == 1
        assert dist["7-8"] == 1
        assert dist["9-10"] == 1

    def test_hard_case_operations(self, eval_mgr):
        """难例应支持增/查/标记已审核/列过滤。"""
        import asyncio
        case_data = {
            "user_id": "u1", "message": "test", "original_answer": "bad",
            "golden_answer": "", "score": 3, "timestamp": "2026-05-01T00:00:00+00:00",
            "reviewed": False,
        }
        case_id = asyncio.run(eval_mgr.add_hard_case(case_data))
        assert case_id

        # 列未审核
        cases = asyncio.run(eval_mgr.list_hard_cases(reviewed=False))
        assert len(cases) == 1

        # 标记已审核
        ok = asyncio.run(eval_mgr.mark_case_reviewed(case_id))
        assert ok

        # 列已审核
        cases = asyncio.run(eval_mgr.list_hard_cases(reviewed=True))
        assert len(cases) == 1

    def test_feedback_operations(self, eval_mgr):
        """反馈应支持增/列过滤/统计。"""
        import asyncio
        asyncio.run(eval_mgr.add_feedback({
            "user_id": "u1", "thumbs_up": True,
            "timestamp": "2026-05-01T00:00:00+00:00",
        }))
        asyncio.run(eval_mgr.add_feedback({
            "user_id": "u1", "thumbs_up": False,
            "timestamp": "2026-05-02T00:00:00+00:00",
        }))
        asyncio.run(eval_mgr.add_feedback({
            "user_id": "u2", "thumbs_up": True,
            "timestamp": "2026-05-03T00:00:00+00:00",
        }))

        stats = asyncio.run(eval_mgr.get_feedback_stats())
        assert stats["thumbs_up"] == 2
        assert stats["thumbs_down"] == 1
        assert stats["total"] == 3

        # 按用户过滤
        items = asyncio.run(eval_mgr.list_feedback(user_id="u1"))
        assert len(items) == 2

    def test_purge_expired_runs(self, eval_mgr):
        """应删除超过保留期的评估记录。"""
        import asyncio
        from datetime import datetime, timedelta, timezone

        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        new_ts = datetime.now(timezone.utc).isoformat()

        asyncio.run(eval_mgr.add_eval_run({
            "user_id": "u1", "overall_score": 5, "timestamp": old_ts,
        }))
        asyncio.run(eval_mgr.add_eval_run({
            "user_id": "u1", "overall_score": 8, "timestamp": new_ts,
        }))

        purged = asyncio.run(eval_mgr.purge_expired_runs(retention_days=30))
        assert purged == 1

    def test_cap_max_runs(self, eval_mgr):
        """超出上限时应删除最旧的记录。"""
        import asyncio
        for i in range(10):
            asyncio.run(eval_mgr.add_eval_run({
                "user_id": "u1", "overall_score": i,
                "timestamp": f"2026-05-{i+1:02d}T00:00:00+00:00",
            }))

        removed = asyncio.run(eval_mgr.cap_max_runs(max_runs=5))
        assert removed == 5
        assert len(eval_mgr.eval_runs_kv._data) == 5

    def test_delete_eval_runs_resets_stats(self, eval_mgr):
        """删除所有记录应重置统计。"""
        import asyncio
        asyncio.run(eval_mgr.update_stats(7))
        count = asyncio.run(eval_mgr.delete_eval_runs())
        assert count == 0  # 没有 eval_run 记录，只有 stats
        summary = asyncio.run(eval_mgr.get_eval_summary())
        assert summary["total_eval_runs"] == 0


# ---- API 端点测试 ----


class TestEvalAPI:
    """测试评估和反馈 REST API。"""

    @pytest.fixture
    def client(self, tmp_path):
        from app.main import create_app
        app = create_app()

        from app.agent.eval.eval_manager import EvalManager
        import asyncio
        mgr = EvalManager(str(tmp_path))
        asyncio.run(mgr.initialize())

        with mock.patch("app.main.get_eval_manager") as m:
            m.return_value = mgr
            with mock.patch("app.main.get_memory_manager") as m2:
                m2.return_value = None
                with mock.patch("app.main.get_storage_manager") as m3:
                    m3.return_value = None
                    # 跳过 lifespan 中 chat.get_graph() 的调用，避免污染全局 _agent_graph
                    with mock.patch("app.main.chat.get_graph") as m4:
                        with TestClient(app) as c:
                            yield c

        asyncio.run(mgr.finalize())

    def test_get_eval_summary_empty(self, client):
        """无数据时应返回零值。"""
        resp = client.get("/eval/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_eval_runs"] == 0
        assert data["avg_score"] == 0.0

    def test_get_eval_runs_empty(self, client):
        """无数据时应返回空列表。"""
        resp = client.get("/eval/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_get_hard_cases_empty(self, client):
        """无难例时应返回空列表。"""
        resp = client.get("/eval/hard-cases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cases"] == []
        assert data["total"] == 0

    def test_post_feedback_thumbs_up(self, client):
        """提交 👍 反馈应成功。"""
        resp = client.post("/feedback", json={
            "user_id": "u1", "thumbs_up": True,
            "message": "你好", "answer": "你好！",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["thumbs_up"] is True
        assert data["user_id"] == "u1"

    def test_post_feedback_thumbs_down(self, client):
        """提交 👎 反馈应成功。"""
        resp = client.post("/feedback", json={
            "user_id": "u1", "thumbs_up": False,
            "comment": "回答不够准确",
            "message": "query", "answer": "bad answer",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["thumbs_up"] is False
        assert data["comment"] == "回答不够准确"

    def test_get_feedback_stats(self, client):
        """反馈统计应正确计数。"""
        client.post("/feedback", json={"user_id": "u1", "thumbs_up": True, "message": "m", "answer": "a"})
        client.post("/feedback", json={"user_id": "u1", "thumbs_up": False, "message": "m", "answer": "a"})
        client.post("/feedback", json={"user_id": "u2", "thumbs_up": True, "message": "m", "answer": "a"})

        resp = client.get("/feedback/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thumbs_up"] == 2
        assert data["thumbs_down"] == 1
        assert data["total"] == 3

    def test_get_feedback_filtered_by_user(self, client):
        """按用户过滤反馈列表。"""
        client.post("/feedback", json={"user_id": "u1", "thumbs_up": True, "message": "m", "answer": "a"})
        client.post("/feedback", json={"user_id": "u2", "thumbs_up": False, "message": "m", "answer": "a"})

        resp = client.get("/feedback?user_id=u1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["feedback"]) == 1

    def test_get_eval_run_not_found(self, client):
        """查找不存在的评估记录应返回 404。"""
        resp = client.get("/eval/runs/nonexistent")
        assert resp.status_code == 404

    def test_get_hard_case_not_found(self, client):
        """查找不存在的难例应返回 404。"""
        resp = client.get("/eval/hard-cases/nonexistent")
        assert resp.status_code == 404

    def test_mark_hard_case_reviewed_not_found(self, client):
        """标记不存在的难例应返回 404。"""
        resp = client.patch("/eval/hard-cases/nonexistent/review")
        assert resp.status_code == 404

    def test_delete_eval_runs(self, client):
        """删除评估记录。"""
        resp = client.delete("/eval/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True

    def test_delete_hard_cases(self, client):
        """删除难例。"""
        resp = client.delete("/eval/hard-cases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True


# ---- 集成测试 ----


class TestEvalIntegration:
    """测试 Chat 端点与评估系统的集成（验证评估触发逻辑本身）。"""

    @pytest.mark.asyncio
    async def test_trigger_eval_creates_task(self, mock_llm):
        """_trigger_eval 在 eval 启用时应创建 asyncio Task 且不崩溃。"""
        from app.api.routes.chat import _trigger_eval
        from app.domain.schemas import ChatRequest
        from app.agent.eval.eval_manager import EvalManager
        import tempfile

        # 设置 FakeLLM 返回合法的评估 JSON
        fake_llm = mock_llm.return_value
        fake_llm._responses = [
            '```json\n{"faithfulness":{"score":8,"passed":true,"feedback":""},"relevance":{"score":7,"passed":true,"feedback":""},"completeness":{"score":6,"passed":true,"feedback":""},"overall_score":7,"is_hard_case":false,"summary":"good"}\n```'
        ]

        with mock.patch("app.agent.eval.evaluator.create_llm") as m_eval:
            m_eval.return_value = fake_llm
            with mock.patch("app.agent.eval.hard_case_miner.create_llm") as m_miner:
                m_miner.return_value = fake_llm
                with tempfile.TemporaryDirectory() as tmpdir:
                    mgr = EvalManager(str(tmpdir))
                    await mgr.initialize()

                    with mock.patch("app.main.get_eval_manager") as m:
                        m.return_value = mgr
                        req = ChatRequest(message="hello", user_id="u1")
                        task = _trigger_eval(req, {"final_answer": "hi"}, [])
                        assert task is not None
                        await task
                        # 验证 eval run 已存储
                        summary = await mgr.get_eval_summary()
                        assert summary["total_eval_runs"] == 1
                        assert summary["avg_score"] > 0

                    await mgr.finalize()

    def test_trigger_eval_disabled(self, mock_llm):
        """_trigger_eval 在 eval 禁用时应返回 None。"""
        from app.api.routes.chat import _trigger_eval
        from app.domain.schemas import ChatRequest

        with mock.patch("app.config.settings.get_settings") as m_settings:
            m_settings.return_value.eval_enabled = False
            req = ChatRequest(message="hello", user_id="u1")
            result = _trigger_eval(req, {"final_answer": "hi"}, [])
            assert result is None


# ---- 配置回退测试 ----


class TestEvalConfigFallback:
    """测试评估功能禁用或管理器为空时的回退行为。"""

    def test_trigger_eval_no_manager(self, mock_llm):
        """EvalManager 未初始化时应返回 None。"""
        with mock.patch("app.main.get_eval_manager") as m:
            m.return_value = None
            from app.api.routes.chat import _trigger_eval
            from app.domain.schemas import ChatRequest

            req = ChatRequest(message="hello", user_id="u1")
            result = _trigger_eval(req, {"final_answer": "hi"}, [])
            assert result is None


# ---- 硬编码阈值测试 ----

class TestHardCaseMiner:
    """测试难例挖掘逻辑。"""

    def test_generate_golden_answer_no_model(self):
        """无 golden_model 配置时应返回空字符串。"""
        import asyncio
        from app.agent.eval.hard_case_miner import generate_golden_answer

        result = asyncio.run(generate_golden_answer(
            user_message="test",
            original_answer="bad",
            worker_results=[],
            golden_model=None,
        ))
        assert result == ""

    def test_generate_golden_answer_empty_string(self):
        """golden_model 为空字符串时也应返回空。"""
        import asyncio
        from app.agent.eval.hard_case_miner import generate_golden_answer

        result = asyncio.run(generate_golden_answer(
            user_message="test",
            original_answer="bad",
            worker_results=[],
            golden_model="",
        ))
        assert result == ""
