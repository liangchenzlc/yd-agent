from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_login_and_chat(monkeypatch, tmp_path):
    from app.web import main
    from app.web.auth import ensure_default_admin
    from app.web.db import WebDatabase

    test_db = WebDatabase(tmp_path / "web.db")
    monkeypatch.setattr(main, "db", test_db)
    monkeypatch.setattr("app.web.auth.db", test_db)
    monkeypatch.setattr("app.web.chat_service.db", test_db)
    monkeypatch.setattr("app.api.routes.user.db", test_db)
    monkeypatch.setattr("app.api.routes.admin.db", test_db)
    test_db.initialize()
    ensure_default_admin()

    async def fake_chat_turn(user, message, session_id=None):
        resolved_session_id = session_id or "session-test"
        test_db.ensure_session(user["id"], resolved_session_id, message[:40])
        test_db.add_message(resolved_session_id, user["id"], "user", message)
        test_db.add_message(resolved_session_id, user["id"], "assistant", "测试回答")
        qa_log = test_db.add_qa_log(
            resolved_session_id,
            user["id"],
            message,
            "测试回答",
            ["retrieval"],
            "测试路由",
            [{"worker": "retrieval", "content": "source"}],
            confidence=0.8,
        )
        return {
            "answer": "测试回答",
            "session_id": resolved_session_id,
            "qa_log_id": qa_log["id"],
            "workers_used": ["retrieval"],
            "dispatch_reasoning": "测试路由",
            "worker_results": [{"worker": "retrieval", "content": "source"}],
        }

    monkeypatch.setattr("app.api.routes.user.run_chat_turn", fake_chat_turn)

    with TestClient(main.app) as client:
        unauthorized = client.get("/api/me")
        assert unauthorized.status_code == 401

        logged_in = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert logged_in.status_code == 200
        token = logged_in.json()["token"]
        assert token.count(".") == 2
        assert logged_in.json()["user"]["role"] == "admin"

        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/me", headers=headers)
        assert me.status_code == 200

        response = client.post("/api/chat", json={"message": "入职试用期多长"}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "测试回答"
        assert body["workers_used"] == ["retrieval"]

        messages = client.get(f"/api/sessions/{body['session_id']}/messages", headers=headers)
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()] == ["user", "assistant"]

        feedback = client.post(
            "/api/feedback",
            json={"qa_log_id": body["qa_log_id"], "rating": -1, "comment": "不准确"},
            headers=headers,
        )
        assert feedback.status_code == 200

        created = client.post(
            "/api/admin/users",
            json={"username": "bob", "password": "pw", "role": "employee"},
            headers=headers,
        )
        assert created.status_code == 200
        assert created.json()["username"] == "bob"

        users = client.get("/api/admin/users", headers=headers)
        assert users.status_code == 200
        assert {item["username"] for item in users.json()} == {"admin", "bob"}

        disabled = client.patch(
            f"/api/admin/users/{created.json()['id']}",
            json={"enabled": False},
            headers=headers,
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False

        denied = client.post("/api/auth/login", json={"username": "bob", "password": "pw"})
        assert denied.status_code == 403


def test_register_endpoint_removed(monkeypatch, tmp_path):
    from app.web import main
    from app.web.auth import ensure_default_admin
    from app.web.db import WebDatabase

    test_db = WebDatabase(tmp_path / "web.db")
    monkeypatch.setattr(main, "db", test_db)
    monkeypatch.setattr("app.web.auth.db", test_db)
    monkeypatch.setattr("app.api.routes.user.db", test_db)
    monkeypatch.setattr("app.api.routes.admin.db", test_db)
    test_db.initialize()
    ensure_default_admin()

    with TestClient(main.app) as client:
        response = client.post("/api/auth/register", json={"username": "bob", "password": "secret123"})

    assert response.status_code == 404
