from __future__ import annotations

import subprocess
import time
from typing import Any, Callable

from app.agent.tools.base import BaseTool


class BashTool(BaseTool):
    """执行 CLI 命令，执行前触发用户确认。"""

    name = "bash"
    description = "在本地终端执行 CLI 命令，执行前需要用户确认"

    def __init__(self, confirm_callback: Callable[[str], bool] | None = None):
        self.confirm_callback = confirm_callback or (lambda cmd: True)

    def run(
        self,
        command: str,
        timeout: int = 30,
        workdir: str | None = None,
    ) -> dict[str, Any]:
        if not self.confirm_callback(command):
            return {
                "success": False,
                "error": "用户取消了命令执行",
                "command": command,
            }

        try:
            proc = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                timeout=timeout,
            )
            return {
                "success": proc.returncode == 0,
                "stdout": proc.stdout.decode("utf-8", errors="replace") if proc.stdout else "",
                "stderr": proc.stderr.decode("utf-8", errors="replace") if proc.stderr else "",
                "exit_code": proc.returncode,
                "command": command,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"命令执行超时 ({timeout}s)",
                "command": command,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": command,
            }
