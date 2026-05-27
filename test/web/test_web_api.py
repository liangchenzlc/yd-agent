from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_login_and_chat(monkeypatch, tmp_path):
    from app.web import main
    from app.web.auth import ensure_super_admin
    from app.web.db import WebDatabase

    test_db = WebDatabase(tmp_path / "web.db")
    monkeypatch.setattr(main, "db", test_db)
    monkeypatch.setattr("app.web.auth.db", test_db)
    monkeypatch.setattr("app.web.chat_service.db", test_db)
    monkeypatch.setattr("app.api.routes.user.db", test_db)
    monkeypatch.setattr("app.api.routes.admin.db", test_db)
    test_db.initialize()
    ensure_super_admin()

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
            "artifacts": [],
        }

    monkeypatch.setattr("app.api.routes.user.run_chat_turn", fake_chat_turn)

    with TestClient(main.app) as client:
        unauthorized = client.get("/api/me")
        assert unauthorized.status_code == 401

        logged_in = client.post("/api/auth/login", json={"username": "super_admin", "password": "super_admin"})
        assert logged_in.status_code == 200
        token = logged_in.json()["token"]
        assert token.count(".") == 2
        assert logged_in.json()["user"]["role"] == "super_admin"

        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/me", headers=headers)
        assert me.status_code == 200

        response = client.post("/api/chat", json={"message": "入职试用期多长"}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "测试回答"
        assert body["workers_used"] == ["retrieval"]
        assert "artifacts" in body

        messages = client.get(f"/api/sessions/{body['session_id']}/messages", headers=headers)
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()] == ["user", "assistant"]


def test_register_endpoint_removed(monkeypatch, tmp_path):
    from app.web import main
    from app.web.auth import ensure_super_admin
    from app.web.db import WebDatabase

    test_db = WebDatabase(tmp_path / "web.db")
    monkeypatch.setattr(main, "db", test_db)
    monkeypatch.setattr("app.web.auth.db", test_db)
    monkeypatch.setattr("app.api.routes.user.db", test_db)
    monkeypatch.setattr("app.api.routes.admin.db", test_db)
    test_db.initialize()
    ensure_super_admin()

    with TestClient(main.app) as client:
        response = client.post("/api/auth/register", json={"username": "bob", "password": "secret123"})

    assert response.status_code == 404


def test_artifact_download_auth_and_permissions(monkeypatch, tmp_path):
    """测试产物下载接口的鉴权和权限控制。"""
    from app.web import main
    from app.web.auth import ensure_super_admin, hash_password
    from app.web.db import WebDatabase

    test_db = WebDatabase(tmp_path / "web.db")
    monkeypatch.setattr(main, "db", test_db)
    monkeypatch.setattr("app.web.auth.db", test_db)
    monkeypatch.setattr("app.api.routes.user.db", test_db)
    monkeypatch.setattr("app.api.routes.admin.db", test_db)
    test_db.initialize()
    ensure_super_admin()

    # 创建测试用户
    user1 = test_db.create_user("user1", hash_password("pass1"), role="user", tenant_id="default")
    user2 = test_db.create_user("user2", hash_password("pass2"), role="user", tenant_id="default")

    # 创建测试文件
    dest_file = tmp_path / "stored_chart.png"
    dest_file.write_bytes(b"\x89PNG\r\n\x1a\n fake png data")

    # 登记产物
    test_db.add_artifact({
        "id": "art_test_001",
        "tenant_id": "default",
        "user_id": user1["id"],
        "session_id": "session_test",
        "message_id": None,
        "qa_log_id": None,
        "worker": "data_analyst",
        "kind": "image",
        "filename": "chart.png",
        "mime_type": "image/png",
        "size_bytes": 20,
        "storage_path": str(dest_file),
    })

    with TestClient(main.app) as client:
        # 未登录访问 → 401
        resp = client.get("/api/artifacts/art_test_001")
        assert resp.status_code == 401

        # user1 登录
        login1 = client.post("/api/user/login", json={"username": "user1", "password": "pass1"})
        assert login1.status_code == 200
        token1 = login1.json()["token"]
        headers1 = {"Authorization": f"Bearer {token1}"}

        # user1 访问自己的产物 → 200
        resp = client.get("/api/artifacts/art_test_001", headers=headers1)
        assert resp.status_code == 200

        # user1 预览 → 200, inline
        resp = client.get("/api/artifacts/art_test_001?preview=1", headers=headers1)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

        # user2 登录
        login2 = client.post("/api/user/login", json={"username": "user2", "password": "pass2"})
        assert login2.status_code == 200
        token2 = login2.json()["token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        # user2 访问 user1 的产物 → 403
        resp = client.get("/api/artifacts/art_test_001", headers=headers2)
        assert resp.status_code == 403

        # 访问不存在的产物 → 404
        resp = client.get("/api/artifacts/nonexistent", headers=headers1)
        assert resp.status_code == 404


def test_artifact_file_missing(monkeypatch, tmp_path):
    """产物元数据存在但磁盘文件丢失时返回 404。"""
    from app.web import main
    from app.web.auth import ensure_super_admin, hash_password
    from app.web.db import WebDatabase

    test_db = WebDatabase(tmp_path / "web.db")
    monkeypatch.setattr(main, "db", test_db)
    monkeypatch.setattr("app.web.auth.db", test_db)
    monkeypatch.setattr("app.api.routes.user.db", test_db)
    monkeypatch.setattr("app.api.routes.admin.db", test_db)
    test_db.initialize()
    ensure_super_admin()

    user = test_db.create_user("testuser", hash_password("pass"), role="user", tenant_id="default")

    # 登记产物，但 storage_path 指向不存在的文件
    test_db.add_artifact({
        "id": "art_missing",
        "tenant_id": "default",
        "user_id": user["id"],
        "session_id": "session_test",
        "message_id": None,
        "qa_log_id": None,
        "worker": "data_analyst",
        "kind": "image",
        "filename": "missing.png",
        "mime_type": "image/png",
        "size_bytes": 0,
        "storage_path": "/nonexistent/path/missing.png",
    })

    with TestClient(main.app) as client:
        login = client.post("/api/user/login", json={"username": "testuser", "password": "pass"})
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get("/api/artifacts/art_missing", headers=headers)
        assert resp.status_code == 404


def test_session_messages_include_artifacts(monkeypatch, tmp_path):
    """历史消息接口返回消息时包含产物信息。"""
    from app.web import main
    from app.web.auth import ensure_super_admin, hash_password
    from app.web.db import WebDatabase

    test_db = WebDatabase(tmp_path / "web.db")
    monkeypatch.setattr(main, "db", test_db)
    monkeypatch.setattr("app.web.auth.db", test_db)
    monkeypatch.setattr("app.api.routes.user.db", test_db)
    monkeypatch.setattr("app.api.routes.admin.db", test_db)
    test_db.initialize()
    ensure_super_admin()

    user = test_db.create_user("artuser", hash_password("pass"), role="user", tenant_id="default")
    session_id = "sess_art_test"
    test_db.ensure_session(user["id"], session_id, "测试产物会话")

    test_db.add_message(session_id, user["id"], "user", "生成柱状图")
    msg2 = test_db.add_message(session_id, user["id"], "assistant", "图表已生成")

    # 为 assistant 消息登记产物
    test_db.add_artifact({
        "id": "art_in_msg",
        "tenant_id": "default",
        "user_id": user["id"],
        "session_id": session_id,
        "message_id": msg2["id"],
        "qa_log_id": None,
        "worker": "data_analyst",
        "kind": "image",
        "filename": "bar.png",
        "mime_type": "image/png",
        "size_bytes": 1024,
        "storage_path": "/tmp/bar.png",
    })

    with TestClient(main.app) as client:
        login = client.post("/api/user/login", json={"username": "artuser", "password": "pass"})
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        assert messages.status_code == 200
        msgs = messages.json()
        assert len(msgs) == 2

        # user 消息无产物
        assert msgs[0]["artifacts"] == []

        # assistant 消息有产物
        assert len(msgs[1]["artifacts"]) == 1
        art = msgs[1]["artifacts"][0]
        assert art["id"] == "art_in_msg"
        assert art["kind"] == "image"
        assert art["filename"] == "bar.png"
        assert art["url"] == "/api/artifacts/art_in_msg"
        assert art["previewUrl"] == "/api/artifacts/art_in_msg?preview=1"
