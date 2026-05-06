import os
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def env_setup():
    """测试环境变量。"""
    os.environ["LLM_API_KEY"] = "test-key"
    os.environ["LLM_BASE_URL"] = "http://fake-llm"
    os.environ["LLM_MODEL"] = "test-model"
    os.environ["EMBEDDING_MODEL"] = "test-embed"
    os.environ["STORAGE_DIR"] = "/tmp/yd-agent-test"
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


class FakeEmbeddings:
    """模拟 Embeddings，返回固定维度的随机向量。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import numpy as np
        return [np.random.randn(128).tolist() for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        import numpy as np
        return np.random.randn(128).tolist()


@pytest.fixture
def mock_embeddings():
    """Mock create_embeddings，返回 FakeEmbeddings。"""
    with mock.patch("app.agent.llm.factory.create_embeddings") as m:
        m.return_value = FakeEmbeddings()
        yield m


@pytest.fixture
def mock_storage():
    """Mock StorageManager，避免真实的持久化操作。"""
    from app.agent.storage_manager import StorageManager

    with mock.patch("app.main.get_storage_manager") as m:
        mgr = StorageManager("/tmp/yd-agent-test", embedding_dim=128)
        m.return_value = mgr
        yield m
