"""测试 Code Worker 节点（真实 LLM + 真实 Docker 沙箱）。"""

from app.agent.tools import ToolRegistry
from app.agent.nodes.code_worker import code_worker_node
from app.agent.constants import WORKER_CODE
from test.helpers import make_initial_state, docker_available

# Docker 不可用时跳过所有测试
import pytest
pytestmark = pytest.mark.skipif(not docker_available(), reason="Docker 不可用")


def setup_module():
    ToolRegistry.init_defaults()


def test_code_worker_returns_structured_result():
    """代码请求 → LLM 通过 ReAct 生成并执行代码 → 返回结果。"""
    state = make_initial_state("用 Python 打印 hello world")
    result = code_worker_node(state)

    assert "worker_results" in result
    assert len(result["worker_results"]) == 1
    wr = result["worker_results"][0]
    assert wr["worker"] == WORKER_CODE
    assert wr["error"] is None
    assert wr["content"] is not None
    assert len(wr["content"]) > 0
    assert "hello" in wr["content"].lower() or "Hello" in wr["content"] or "world" in wr["content"].lower()
