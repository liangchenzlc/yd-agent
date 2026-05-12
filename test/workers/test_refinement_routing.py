from app.agent.graph import route_to_workers
from app.agent.nodes.summary_worker import summary_worker_node
from test.helpers import make_initial_state


def test_route_to_workers_prefers_refinement_targets():
    state = make_initial_state("fix it")
    state["worker_assignments"] = ["retrieval"]
    state["refinement_targets"] = ["code"]

    sends = route_to_workers(state)

    assert [send.node for send in sends] == ["code_worker"]


def test_summary_uses_only_current_refinement_results(monkeypatch):
    class FakeLLM:
        def invoke(self, prompt):
            assert "old result" not in prompt
            assert "new result" in prompt

            class Response:
                content = "final"

            return Response()

    monkeypatch.setattr("app.agent.nodes.summary_worker.llm_factory.create_llm", lambda: FakeLLM())

    state = make_initial_state("question")
    state["refinement_count"] = 1
    state["worker_results"] = [
        {
            "worker": "retrieval",
            "content": "old result",
            "error": None,
            "metadata": {"refinement_count": 0},
        },
        {
            "worker": "retrieval",
            "content": "new result",
            "error": None,
            "metadata": {"refinement_count": 1},
        },
    ]

    assert summary_worker_node(state)["final_answer"] == "final"
