"""测试 Chat API（真实 LLM）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_chat_simple_greeting(client):
    """问候语 → Supervisor 路由到 summary → 返回回答。"""
    resp = client.post("/chat", json={"message": "你好"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert "workers_used" in data


def test_chat_empty_message(client):
    """空消息 → Pydantic 校验返回 422。"""
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_stream(client):
    """SSE 流式接口 → 返回 text/event-stream。"""
    resp = client.post("/chat/stream", json={"message": "你好"}, timeout=90)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
