"""测试 DockerSandBoxTool（真实 Docker 沙箱）。"""

from app.agent.tools.docker_sandbox_tool import DockerSandBoxTool
from test.helpers import skip_if_no_docker


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
