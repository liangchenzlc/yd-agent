"""测试 DockerSandBoxTool（真实 Docker 沙箱）。"""

from app.agent.sandbox.docker_sandbox import SandboxResult
from app.agent.tools.docker_sandbox_tool import DockerSandBoxTool
from test.helpers import skip_if_no_docker


def test_run_code_formats_stdout_and_stderr(monkeypatch):
    def fake_run_code(code: str, timeout: int):
        return SandboxResult(stdout="out\n", stderr="err\n", exit_code=0, timed_out=False)

    monkeypatch.setattr("app.agent.tools.docker_sandbox_tool.docker_sandbox.run_code", fake_run_code)

    result = DockerSandBoxTool().run_code("print('x')")

    assert result == "out\n\n[stderr]\nerr"


def test_run_code_stdout():
    skip_if_no_docker()
    tool = DockerSandBoxTool()
    result = tool.run_code("print(42)")
    assert "42" in result


def test_run_code_stderr():
    skip_if_no_docker()
    tool = DockerSandBoxTool()
    result = tool.run_code("import sys; print('hello', file=sys.stderr)")
    assert "[stderr]" in result
    assert "hello" in result


def test_run_code_nonzero_exit():
    skip_if_no_docker()
    tool = DockerSandBoxTool()
    result = tool.run_code("raise ValueError('boom')")
    assert "进程退出码" in result or "ValueError" in result or "boom" in result


def test_run_code_empty_output():
    skip_if_no_docker()
    tool = DockerSandBoxTool()
    result = tool.run_code("x = 1")
    assert result == "[代码执行完成，无输出]"
