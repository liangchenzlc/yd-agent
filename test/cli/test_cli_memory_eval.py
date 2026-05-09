class FakeMemoryVDB:
    def __init__(self, items):
        self._id_to_meta = items
        self.deleted = []

    def delete(self, ids):
        self.deleted.extend(ids)
        for item_id in ids:
            self._id_to_meta.pop(item_id, None)


class FakeMemoryManager:
    def __init__(self):
        self.core_memory_vdb = FakeMemoryVDB({
            "core1": {
                "text": "preference: 喜欢简洁回答",
                "metadata": {"user_id": "alice", "type": "preference", "importance": 0.9, "timestamp": "2026-05-09"},
            }
        })
        self.working_memory_vdb = FakeMemoryVDB({
            "work1": {
                "text": "fact: 正在做 CLI 改造",
                "metadata": {"user_id": "alice", "type": "fact", "importance": 0.5, "timestamp": "2026-05-09"},
            }
        })
        self.forgotten = []

    async def forget_user(self, user_id):
        self.forgotten.append(user_id)

    async def get_user_profile(self, user_id):
        return {"user_id": user_id, "topics": {"cli": 2}, "total_interactions": 3, "last_active": "2026-05-09"}


class FakeEvalManager:
    async def get_eval_summary(self):
        return {"total_eval_runs": 2, "total_hard_cases": 1, "avg_score": 8.5, "pass_rate": 1.0}

    async def list_eval_runs(self, limit=50, offset=0, min_score=0, max_score=10):
        return [{"run_id": "r1", "user_id": "alice", "message": "你好", "answer": "你好", "overall_score": 9, "timestamp": "2026-05-09"}]

    async def count_eval_runs(self, min_score=0, max_score=10):
        return 1

    async def list_hard_cases(self, reviewed=None, limit=50, offset=0):
        return [{"case_id": "c1", "user_id": "alice", "message": "难题", "score": 4, "reviewed": False, "timestamp": "2026-05-09"}]

    async def count_hard_cases(self, reviewed=None):
        return 1


class FakeRuntime:
    def __init__(self):
        self.storage_manager = object()
        self.memory_manager = FakeMemoryManager()
        self.eval_manager = FakeEvalManager()
        self.graph = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def install_runtime(monkeypatch):
    import app.cli as cli
    from rich.console import Console

    runtime = FakeRuntime()
    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(cli, "console", console)
    monkeypatch.setattr(cli, "AgentRuntime", lambda: runtime)
    return cli, console, runtime


def test_memory_list_prints_core_and_working_memories(monkeypatch):
    cli, console, _ = install_runtime(monkeypatch)

    code = cli.main(["memory", "list", "--user-id", "alice"])

    output = console.export_text()
    assert code == 0
    assert "core1" in output
    assert "work1" in output
    assert "喜欢简洁回答" in output


def test_memory_clear_requires_confirmation_and_forgets_user(monkeypatch):
    cli, console, runtime = install_runtime(monkeypatch)

    assert cli.main(["memory", "clear", "--user-id", "alice"]) == 2
    assert runtime.memory_manager.forgotten == []

    assert cli.main(["memory", "clear", "--user-id", "alice", "--yes"]) == 0
    assert runtime.memory_manager.forgotten == ["alice"]
    assert "deleted" in console.export_text()


def test_profile_show_prints_user_profile(monkeypatch):
    cli, console, _ = install_runtime(monkeypatch)

    code = cli.main(["profile", "show", "--user-id", "alice"])

    output = console.export_text()
    assert code == 0
    assert "alice" in output
    assert "cli" in output
    assert "3" in output


def test_eval_summary_runs_and_hard_cases(monkeypatch):
    cli, console, _ = install_runtime(monkeypatch)

    assert cli.main(["eval", "summary"]) == 0
    assert cli.main(["eval", "runs", "--limit", "5", "--min-score", "6"]) == 0
    assert cli.main(["eval", "hard-cases", "--reviewed", "false"]) == 0

    output = console.export_text()
    assert "total_eval_runs" in output
    assert "r1" in output
    assert "c1" in output
