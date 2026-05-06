from fastapi.testclient import TestClient
from unittest import mock

from app.main import app
from test.mock_utils import FakeLLM, fake_run_code, SUPERVISOR_SUMMARY_JSON, SUPERVISOR_CODE_JSON, DEFAULT_ANSWER

client = TestClient(app)


def test_chat_simple_greeting():
    """简单问候 → Supervisor 路由到 summary → 返回回答。"""
    with mock.patch("app.agent.llm.factory.create_llm") as m_llm, \
         mock.patch("app.agent.sandbox.docker_sandbox.run_code") as m_docker:
        # Supervisor 选 summary，summary 直接回答，refiner 用 fallback
        m_llm.return_value = FakeLLM([SUPERVISOR_SUMMARY_JSON, None, None])
        m_docker.side_effect = fake_run_code

        resp = client.post("/chat", json={"message": "你好"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert len(data["answer"]) > 0
        assert "workers_used" in data


def test_chat_code_execution():
    """代码请求 → Supervisor 路由到 code → 返回执行结果。"""
    with mock.patch("app.agent.llm.factory.create_llm") as m_llm, \
         mock.patch("app.agent.sandbox.docker_sandbox.run_code") as m_docker:
        from app.agent.sandbox.docker_sandbox import SandboxResult

        # Supervisor 选 code，code worker 返回代码，summary 用 fallback，refiner 用 fallback
        m_llm.return_value = FakeLLM([SUPERVISOR_CODE_JSON, None, None, None])
        m_docker.return_value = SandboxResult(
            stdout="42", stderr="", exit_code=0, timed_out=False
        )

        resp = client.post("/chat", json={"message": "用 Python 计算 1+1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data


def test_chat_empty_message():
    """空消息 → 返回 422（Pydantic 校验）。"""
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_chat_stream():
    """SSE 流式接口 → 返回 text/event-stream。"""
    with mock.patch("app.agent.llm.factory.create_llm") as m_llm, \
         mock.patch("app.agent.sandbox.docker_sandbox.run_code"):
        m_llm.return_value = FakeLLM([SUPERVISOR_SUMMARY_JSON, None, None])

        resp = client.post("/chat/stream", json={"message": "你好"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "supervisor" in body
        assert "done" in body
