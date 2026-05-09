"""测试 Supervisor 节点（真实 LLM）。"""

from app.agent.nodes.supervisor import supervisor_node
from app.agent.constants import ALL_WORKERS
from test.helpers import make_initial_state


def test_supervisor_routes_summary_for_greeting():
    """问候语 → LLM 分配到 summary。"""
    state = make_initial_state("你好")
    result = supervisor_node(state)

    assert "worker_assignments" in result
    assert len(result["worker_assignments"]) > 0
    for w in result["worker_assignments"]:
        assert w in ALL_WORKERS
    assert "dispatch_reasoning" in result
    assert result["worker_results"] == []


def test_supervisor_routes_code_for_computation():
    """计算请求 → LLM 分配到 code。"""
    state = make_initial_state("用 Python 计算 1+1")
    result = supervisor_node(state)

    assert "code" in result["worker_assignments"]


def test_supervisor_clears_previous_results():
    """确保每次调度清空上次的 worker_results。"""
    state = make_initial_state("你好")
    state["worker_results"] = [{"worker": "code", "content": "old"}]
    result = supervisor_node(state)

    assert result["worker_results"] == []


def test_supervisor_returns_valid_workers_only():
    """LLM 返回的 worker 名称必须在 ALL_WORKERS 中。"""
    state = make_initial_state("帮我查一下资料")
    result = supervisor_node(state)

    for w in result["worker_assignments"]:
        assert w in ALL_WORKERS
