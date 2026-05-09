"""测试 Summary Worker 节点（真实 LLM）。"""

from app.agent.nodes.summary_worker import summary_worker_node
from test.helpers import make_initial_state


def test_summary_worker_with_results():
    """有 Worker 结果时生成汇总回答。"""
    state = make_initial_state("你好")
    state["worker_results"] = [
        {"worker": "retrieval", "content": "找到相关信息", "error": None},
        {"worker": "code", "content": "计算结果: 42", "error": None},
    ]
    result = summary_worker_node(state)

    assert "final_answer" in result
    assert len(result["final_answer"]) > 0


def test_summary_worker_no_results():
    """无 Worker 结果时也能正常回答。"""
    state = make_initial_state("你好")
    state["worker_results"] = []
    result = summary_worker_node(state)

    assert "final_answer" in result
    assert len(result["final_answer"]) > 0


def test_summary_worker_with_failed_worker():
    """部分 Worker 失败时如实反映。"""
    state = make_initial_state("计算 1+1")
    state["worker_results"] = [
        {"worker": "code", "content": "", "error": "Execution timed out"},
    ]
    result = summary_worker_node(state)

    assert "final_answer" in result
