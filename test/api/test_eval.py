"""评估系统测试：EvalManager, 反馈 API（真实依赖）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


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
        import asyncio
        summary = asyncio.run(eval_mgr.get_eval_summary())
        assert summary["total_eval_runs"] == 0
        assert summary["avg_score"] == 0.0
        assert summary["pass_rate"] == 0.0
        assert summary["total_hard_cases"] == 0

    def test_add_and_get_eval_run(self, eval_mgr):
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
        import asyncio
        for i in range(5):
            asyncio.run(eval_mgr.add_eval_run({
                "user_id": "u1", "overall_score": i + 1,
                "timestamp": f"2026-05-0{i+1}T00:00:00+00:00",
            }))
        runs = asyncio.run(eval_mgr.list_eval_runs(limit=3, offset=0))
        assert len(runs) == 3
        assert runs[0]["overall_score"] == 5

        runs = asyncio.run(eval_mgr.list_eval_runs(limit=10, min_score=4, max_score=6))
        assert len(runs) == 2

    def test_stats_update(self, eval_mgr):
        import asyncio
        asyncio.run(eval_mgr.update_stats(8))
        asyncio.run(eval_mgr.update_stats(3))
        asyncio.run(eval_mgr.update_stats(9))

        summary = asyncio.run(eval_mgr.get_eval_summary())
        assert summary["total_eval_runs"] == 3
        assert summary["avg_score"] == round((8 + 3 + 9) / 3, 2)
        dist = summary["score_distribution"]
        assert dist["0-3"] == 1
        assert dist["7-8"] == 1
        assert dist["9-10"] == 1

    def test_hard_case_operations(self, eval_mgr):
        import asyncio
        case_data = {
            "user_id": "u1", "message": "test", "original_answer": "bad",
            "golden_answer": "", "score": 3, "timestamp": "2026-05-01T00:00:00+00:00",
            "reviewed": False,
        }
        case_id = asyncio.run(eval_mgr.add_hard_case(case_data))
        assert case_id

        cases = asyncio.run(eval_mgr.list_hard_cases(reviewed=False))
        assert len(cases) == 1

        ok = asyncio.run(eval_mgr.mark_case_reviewed(case_id))
        assert ok

        cases = asyncio.run(eval_mgr.list_hard_cases(reviewed=True))
        assert len(cases) == 1

    def test_feedback_operations(self, eval_mgr):
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

        items = asyncio.run(eval_mgr.list_feedback(user_id="u1"))
        assert len(items) == 2

    def test_purge_expired_runs(self, eval_mgr):
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
        import asyncio
        asyncio.run(eval_mgr.update_stats(7))
        count = asyncio.run(eval_mgr.delete_eval_runs())
        assert count == 0
        summary = asyncio.run(eval_mgr.get_eval_summary())
        assert summary["total_eval_runs"] == 0


class TestEvalAPI:
    """测试评估和反馈 REST API（真实依赖：app lifespan 初始化 EvalManager）。"""

    @pytest.fixture
    def client(self):
        from app.api.routes import chat
        chat._agent_graph = None
        with TestClient(app) as c:
            yield c

    def test_get_eval_summary_empty(self, client):
        resp = client.get("/eval/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_eval_runs"] == 0
        assert data["avg_score"] == 0.0

    def test_get_eval_runs_empty(self, client):
        resp = client.get("/eval/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_get_hard_cases_empty(self, client):
        resp = client.get("/eval/hard-cases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cases"] == []
        assert data["total"] == 0

    def test_post_feedback_thumbs_up(self, client):
        resp = client.post("/feedback", json={
            "user_id": "u1", "thumbs_up": True,
            "message": "你好", "answer": "你好！",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["thumbs_up"] is True
        assert data["user_id"] == "u1"

    def test_post_feedback_thumbs_down(self, client):
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
        client.post("/feedback", json={"user_id": "u1", "thumbs_up": True, "message": "m", "answer": "a"})
        client.post("/feedback", json={"user_id": "u2", "thumbs_up": False, "message": "m", "answer": "a"})

        resp = client.get("/feedback?user_id=u1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["feedback"]) == 1

    def test_get_eval_run_not_found(self, client):
        resp = client.get("/eval/runs/nonexistent")
        assert resp.status_code == 404

    def test_get_hard_case_not_found(self, client):
        resp = client.get("/eval/hard-cases/nonexistent")
        assert resp.status_code == 404

    def test_mark_hard_case_reviewed_not_found(self, client):
        resp = client.patch("/eval/hard-cases/nonexistent/review")
        assert resp.status_code == 404

    def test_delete_eval_runs(self, client):
        resp = client.delete("/eval/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True

    def test_delete_hard_cases(self, client):
        resp = client.delete("/eval/hard-cases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True


class TestHardCaseMiner:
    """测试难例挖掘逻辑。"""

    def test_generate_golden_answer_no_model(self):
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
        import asyncio
        from app.agent.eval.hard_case_miner import generate_golden_answer

        result = asyncio.run(generate_golden_answer(
            user_message="test",
            original_answer="bad",
            worker_results=[],
            golden_model="",
        ))
        assert result == ""
