from __future__ import annotations

import subprocess
from typing import Callable

from app.agent.tools.base import BaseTool, as_tool


class BashTool(BaseTool):
    """Shell 命令执行工具，在本地终端执行 CLI 命令。"""

    name = "bash"
    description = "Shell 命令执行工具，在本地终端执行 CLI 命令"

    def __init__(self, confirm_callback: Callable[[str], bool] | None = None):
        self.confirm_callback = confirm_callback or (lambda cmd: True)

    @as_tool(
        name="run_command",
        description=(
            "在本地终端执行 CLI 命令并返回输出结果。"
            "command 是要执行的 shell 命令字符串，"
            "timeout 是超时秒数（默认 30），"
            "workdir 是工作目录（可选）。"
        ),
    )
    def run_command(self, command: str, timeout: int = 30, workdir: str | None = None) -> str:
        if not self.confirm_callback(command):
            return f"用户取消了命令执行: {command}"

        try:
            proc = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                timeout=timeout,
            )
            output = ""
            if proc.stdout:
                output += proc.stdout.decode("utf-8", errors="replace")[:100_000]
            if proc.stderr:
                if output:
                    output += "\n"
                output += proc.stderr.decode("utf-8", errors="replace")[:50_000]
            if proc.returncode != 0:
                output += f"\n[退出码: {proc.returncode}]"
            return output.strip() or "[命令执行完成，无输出]"
        except subprocess.TimeoutExpired:
            return f"[错误] 命令执行超时 ({timeout}s): {command}"
        except Exception as e:
            return f"[错误] {e}"
