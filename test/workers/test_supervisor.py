from app.agent.constants import ALL_WORKERS
from app.agent.nodes.supervisor import supervisor_node
from test.helpers import make_initial_state


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.prompt = ""

    def invoke(self, prompt: str):
        self.prompt = prompt
        return FakeResponse(self.content)


def patch_llm(monkeypatch, content: str) -> FakeLLM:
    fake = FakeLLM(content)
    monkeypatch.setattr(
        "app.agent.nodes.supervisor.llm_factory.create_llm",
        lambda: fake,
    )
    return fake


def test_supervisor_routes_summary_for_greeting(monkeypatch):
    fake = patch_llm(
        monkeypatch,
        '{"workers": ["summary"], "reasoning": "简单问候"}',
    )
    state = make_initial_state("你好")

    result = supervisor_node(state)

    assert result["worker_assignments"] == ["summary"]
    assert result["dispatch_reasoning"] == "简单问候"
    assert result["worker_results"] == []
    assert "你好" in fake.prompt


def test_supervisor_routes_code_for_computation(monkeypatch):
    patch_llm(
        monkeypatch,
        '{"workers": ["code"], "reasoning": "需要执行 Python 计算"}',
    )
    state = make_initial_state("用 Python 写一个累加函数")

    result = supervisor_node(state)

    assert "code" in result["worker_assignments"]


def test_supervisor_clears_previous_results(monkeypatch):
    patch_llm(
        monkeypatch,
        '{"workers": ["summary"], "reasoning": "普通对话"}',
    )
    state = make_initial_state("你好")
    state["worker_results"] = [{"worker": "code", "content": "old"}]

    result = supervisor_node(state)

    assert result["worker_results"] == []


def test_supervisor_returns_valid_workers_only(monkeypatch):
    patch_llm(
        monkeypatch,
        '{"workers": ["retrieval", "unknown"], "reasoning": "需要查资料"}',
    )
    state = make_initial_state("帮我查一下资料")

    result = supervisor_node(state)

    assert result["worker_assignments"] == ["retrieval"]
    for worker in result["worker_assignments"]:
        assert worker in ALL_WORKERS


def test_supervisor_uses_refinement_targets_without_llm(monkeypatch):
    def fail_create_llm():
        raise AssertionError("LLM should not be called for refinement routing")

    monkeypatch.setattr("app.agent.nodes.supervisor.llm_factory.create_llm", fail_create_llm)
    state = make_initial_state("修一下")
    state["refinement_targets"] = ["code", "unknown"]
    state["refinement_feedback"] = "上一轮代码结果不对"

    result = supervisor_node(state)

    assert result["worker_assignments"] == ["code"]
    assert result["dispatch_reasoning"] == "上一轮代码结果不对"
    assert result["refinement_targets"] == []
