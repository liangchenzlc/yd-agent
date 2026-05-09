"""测试 Retrieval Worker 节点（真实 LLM + 真实 SearchTool）。"""

from app.agent.tools import ToolRegistry
from app.agent.nodes.retrieval_worker import retrieval_worker_node
from app.agent.constants import WORKER_RETRIEVAL
from test.helpers import make_initial_state


def setup_module():
    ToolRegistry.init_defaults()


def test_retrieval_worker_without_storage_manager():
    """无 storage_manager → SearchTool 返回无文档提示 → LLM 据此回答。"""
    state = make_initial_state("搜索资料")
    result = retrieval_worker_node(state, storage_manager=None)

    assert "worker_results" in result
    assert len(result["worker_results"]) == 1
    wr = result["worker_results"][0]
    assert wr["worker"] == WORKER_RETRIEVAL
    assert wr["error"] is None
    assert wr["content"] is not None
    assert len(wr["content"]) > 0


def test_retrieval_worker_empty_message():
    """空消息也能正常运行，不会崩溃。"""
    state = make_initial_state("")
    result = retrieval_worker_node(state, storage_manager=None)

    assert "worker_results" in result
    assert result["worker_results"][0]["worker"] == WORKER_RETRIEVAL
