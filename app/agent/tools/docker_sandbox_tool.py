from __future__ import annotations

from app.agent.sandbox import docker_sandbox
from app.agent.tools.base import BaseTool, as_tool


class DockerSandBoxTool(BaseTool):
    """Docker 沙箱工具集，用于在隔离环境中执行代码。"""

    name = "docker_sandbox"
    description = "Docker 沙箱工具集，用于在隔离环境中执行代码"

    @as_tool(
        name="run_code",
        description=(
            "在 Docker 沙箱中执行 Python 代码并返回标准输出和标准错误。"
            "适用于运行用户要求的 Python 代码、数据分析、脚本执行等场景。"
            "code 参数是要执行的 Python 代码字符串，timeout 是超时秒数（默认 30）。"
        ),
    )
    def run_code(self, code: str, timeout: int = 30) -> str:
        """Execute Python code in Docker sandbox and return text output."""
        result = docker_sandbox.run_code(code, timeout=timeout)
        parts = []
        if result.stdout:
            parts.append(result.stdout.rstrip())
        if result.stderr:
            if parts:
                parts.append("")
            parts.append(f"[stderr]\n{result.stderr.rstrip()}")
        if result.exit_code != 0:
            parts.append(f"[进程退出码: {result.exit_code}]")
        if result.timed_out:
            parts.append("[执行超时]")
        return "\n".join(parts).strip() or "[代码执行完成，无输出]"
