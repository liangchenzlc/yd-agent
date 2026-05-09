"""测试 BashTool（真实 shell 命令执行）。"""

from app.agent.tools.bash_tool import BashTool


def test_run_command_success():
    tool = BashTool(confirm_callback=lambda cmd: True)
    result = tool.run_command('echo "hello world"')
    assert "hello world" in result


def test_run_command_with_stderr():
    tool = BashTool(confirm_callback=lambda cmd: True)
    result = tool.run_command('echo "out" && echo "err" >&2')
    assert "out" in result
    assert "err" in result


def test_run_command_nonzero_exit():
    tool = BashTool(confirm_callback=lambda cmd: True)
    result = tool.run_command("exit 42")
    assert "退出码: 42" in result


def test_run_command_user_cancelled():
    tool = BashTool(confirm_callback=lambda cmd: False)
    result = tool.run_command("rm -rf /")
    assert "用户取消了" in result


def test_run_command_timeout():
    tool = BashTool(confirm_callback=lambda cmd: True)
    result = tool.run_command("sleep 10", timeout=1)
    assert "超时" in result


def test_run_command_with_workdir(tmp_path):
    tool = BashTool(confirm_callback=lambda cmd: True)
    result = tool.run_command("pwd", workdir=str(tmp_path))
    assert len(result) > 0


def test_run_command_empty_output():
    tool = BashTool(confirm_callback=lambda cmd: True)
    result = tool.run_command("true")
    assert result == "[命令执行完成，无输出]"


def test_run_command_large_output_truncated():
    tool = BashTool(confirm_callback=lambda cmd: True)
    result = tool.run_command("python -c \"print('x' * 200000)\"")
    assert len(result) < 150_000
