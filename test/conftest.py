import os
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def env_setup():
    """测试环境变量。"""
    os.environ["LLM_API_KEY"] = "test-key"
    os.environ["LLM_BASE_URL"] = "http://fake-llm"
    os.environ["LLM_MODEL"] = "test-model"
    # 清除 settings 缓存
    from app.config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_llm():
    """Mock create_llm，使其返回 FakeLLM。"""
    from test.mock_utils import FakeLLM

    with mock.patch("app.agent.llm.factory.create_llm") as m:
        m.return_value = FakeLLM()
        yield m


@pytest.fixture
def mock_docker():
    """Mock Docker 沙箱，返回成功结果。"""
    from test.mock_utils import fake_run_code

    with mock.patch("app.agent.nodes.code_worker.run_code") as m:
        m.side_effect = fake_run_code
        yield m


@pytest.fixture
def mock_httpx():
    """Mock httpx.Client，避免真实网络请求。"""

    class FakeResponse:
        def __init__(self, text="ok", status_code=200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            pass

    with mock.patch("httpx.Client") as m:
        client = m.return_value.__enter__.return_value
        client.request.return_value = FakeResponse()
        yield m
