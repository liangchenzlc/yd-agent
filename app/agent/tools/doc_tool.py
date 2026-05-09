from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.tools.base import BaseTool


class DocTool(BaseTool):
    """将文档内容写入文件系统。"""

    name = "doc"
    description = "将文档内容写入指定文件"

    def __init__(self, base_dir: str = "./docs"):
        self.base_dir = Path(base_dir)

    def run(
        self,
        file_path: str,
        content: str,
        append: bool = False,
    ) -> dict[str, Any]:
        full_path = self.base_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        try:
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "file_path": str(full_path.resolve()),
                "size": len(content),
            }
        except OSError as e:
            return {
                "success": False,
                "error": str(e),
                "file_path": str(full_path),
            }
