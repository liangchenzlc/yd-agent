import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def env_setup():
    """设置测试环境（存储路径隔离，不清除 LLM 配置以使用真实 LLM）。"""
    # 使用临时目录作为存储路径，避免影响真实数据
    tmp = tempfile.mkdtemp(prefix="yd-agent-test-")
    os.environ["STORAGE_DIR"] = tmp
    from app.config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
