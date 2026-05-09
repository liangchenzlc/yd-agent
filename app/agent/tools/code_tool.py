from __future__ import annotations

from typing import Any

from app.agent.sandbox import docker_sandbox
from app.agent.sandbox.docker_sandbox import SandboxError
from app.agent.tools.base import BaseTool


class CodeTool(BaseTool):
    """在 Docker 沙箱中执行 Python 代码。"""

    name = "code"
    description = "在 Docker 沙箱中执行 Python 代码并返回结果"

    def run(self, code: str, timeout: int | None = None) -> dict[str, Any]:
        try:
            result = docker_sandbox.run_code(code, timeout=timeout)
            return {
                "success": result.exit_code == 0,
                "stdout": result.stdout.strip() if result.stdout else "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
            }
        except SandboxError as e:
            return {
                "success": False,
                "error": str(e),
                "exit_code": -1,
            }
