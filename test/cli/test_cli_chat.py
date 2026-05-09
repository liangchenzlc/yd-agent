import json

from rich.console import Console


class FakeGraph:
    async def ainvoke(self, state):
        self.state = state
        return {
            "final_answer": "你好，我是 CLI 助手。",
            "dispatch_reasoning": "普通问答",
            "worker_assignments": ["summary"],
            "worker_results": [],
            "refinement_count": 1,
            "memories_updated": True,
        }


class FakeRuntime:
    def __init__(self):
        self.graph = FakeGraph()
        self.storage_manager = object()
        self.memory_manager = object()
        self.eval_manager = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def run_cli(monkeypatch, argv):
    import app.cli as cli

    console = Console(record=True, width=100, color_system=None)
    monkeypatch.setattr(cli, "console", console)
    monkeypatch.setattr(cli, "AgentRuntime", lambda: FakeRuntime())

    code = cli.main(argv)
    return code, console.export_text()


def test_doctor_prints_runtime_status(monkeypatch):
    code, output = run_cli(monkeypatch, ["doctor"])

    assert code == 0
    assert "yd-Agent" in output
    assert "storage" in output
    assert "llm" in output


def test_chat_json_outputs_structured_response(monkeypatch, capsys):
    import app.cli as cli

    console = Console(record=True, width=100, color_system=None)
    monkeypatch.setattr(cli, "console", console)
    runtime = FakeRuntime()
    monkeypatch.setattr(cli, "AgentRuntime", lambda: runtime)

    code = cli.main(["chat", "你好", "--user-id", "alice", "--session-id", "s1", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "answer": "你好，我是 CLI 助手。",
        "reasoning": "普通问答",
        "workers_used": ["summary"],
        "worker_results": [],
        "refinements": 1,
        "session_id": "s1",
        "memories_updated": True,
    }
    assert runtime.graph.state["user_id"] == "alice"
    assert runtime.graph.state["messages"][0].content == "你好"


def test_chat_text_outputs_rich_answer(monkeypatch):
    code, output = run_cli(monkeypatch, ["chat", "你好"])

    assert code == 0
    assert "你好，我是 CLI 助手。" in output
    assert "Workers" in output
