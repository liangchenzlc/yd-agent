"""测试 Refiner 节点（真实 LLM）。"""

from app.agent.nodes.refiner import refiner_node
from test.helpers import make_initial_state


def test_refiner_passes_good_answer():
    """高质量回答 → Refiner 给出高分，不要求重试。"""
    state = make_initial_state("Python 的列表怎么用")
    state["final_answer"] = (
        "Python 列表用方括号创建，例如 `my_list = [1, 2, 3]`。"
        "支持索引访问、切片、append、extend 等操作。"
    )
    state["worker_results"] = [
        {"worker": "retrieval", "content": "列表是 Python 内置数据结构", "error": None}
    ]
    result = refiner_node(state)

    assert "refinement_needed" in result
    # 高质量回答应该不需要重试
    assert result["refinement_needed"] is False


def test_refiner_respects_max_refinements():
    """达到最大重试次数后不再重试。"""
    state = make_initial_state("test")
    state["final_answer"] = "short"
    state["worker_results"] = []
    state["refinement_count"] = 2  # 已达到上限
    result = refiner_node(state)

    assert result["refinement_needed"] is False
