"""测试 Docs Worker 节点（真实 LLM + 真实文件系统）。"""

from app.agent.tools import ToolRegistry
from app.agent.nodes.docs_worker import docs_worker_node
from app.agent.constants import WORKER_DOCS
from test.helpers import make_initial_state


def setup_module():
    ToolRegistry.init_defaults()


def test_docs_worker_returns_structured_result():
    """写文件请求 → LLM 通过 ReAct 调用 write_file → 返回结果。"""
    state = make_initial_state('写一个 hello.txt 文件，内容为 "Hello World"')
    result = docs_worker_node(state)

    assert "worker_results" in result
    assert len(result["worker_results"]) == 1
    wr = result["worker_results"][0]
    assert wr["worker"] == WORKER_DOCS
    assert wr["error"] is None
    assert wr["content"] is not None
    assert len(wr["content"]) > 0
