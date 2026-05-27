from __future__ import annotations

import os
from pathlib import Path

from app.agent.tools.base import BaseTool, as_tool


class FileTool(BaseTool):
    """File read/write tools scoped to a base directory."""

    name = "file"
    description = "File read/write tools scoped to a local documentation directory"

    _MIME_TYPES = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".html": "text/html",
        ".csv": "text/csv",
        ".json": "application/json",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    def __init__(self, base_dir: str = "./docs", worker: str = "docs"):
        super().__init__()
        self.base_dir = Path(base_dir).resolve()
        self._worker = worker

    def _resolve_inside_base(self, file_path: str) -> Path | None:
        candidate = (self.base_dir / file_path).resolve()
        try:
            candidate.relative_to(self.base_dir)
        except ValueError:
            return None
        return candidate

    def _get_mime_type(self, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        return self._MIME_TYPES.get(suffix, "application/octet-stream")

    def _snapshot_files(self) -> set[str]:
        """快照 base_dir 下所有文件的绝对路径集合。"""
        result = set()
        if not self.base_dir.exists():
            return result
        for f in self.base_dir.rglob("*"):
            if f.is_file():
                result.add(str(f.resolve()))
        return result

    def _collect_new_files(self, before: set[str]) -> None:
        """检测 before 快照之后新增的文件并登记为产物。"""
        if not self.base_dir.exists():
            return
        for f in self.base_dir.rglob("*"):
            if f.is_file() and str(f.resolve()) not in before:
                try:
                    size = f.stat().st_size
                except OSError:
                    size = 0
                # 限制单个文件最大 1GB
                if size > 1024 * 1024 * 1024:
                    continue
                rel = f.relative_to(self.base_dir)
                self.register_artifact(
                    filepath=str(f.resolve()),
                    filename=f.name,
                    mime_type=self._get_mime_type(f.name),
                    kind="file",
                    worker=self._worker,
                    metadata={"relative_path": str(rel)},
                )

    @as_tool(
        name="write_file",
        description="Write content to a file relative to the documentation directory.",
    )
    def write_file(self, file_path: str, content: str, append: bool = False) -> str:
        before = self._snapshot_files()
        full_path = self._resolve_inside_base(file_path)
        if full_path is None:
            return f"Error: file path escapes base directory: {file_path}"
        full_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(full_path, mode, encoding="utf-8") as f:
            f.write(content)
        self._collect_new_files(before)
        return f"文件已保存: {file_path} ({len(content)} 字节)"

    @as_tool(
        name="read_file",
        description="Read a file relative to the documentation directory.",
    )
    def read_file(self, file_path: str) -> str:
        full_path = self._resolve_inside_base(file_path)
        if full_path is None:
            return f"Error: file path escapes base directory: {file_path}"
        if not full_path.exists():
            return f"Error: file does not exist: {file_path}"
        return full_path.read_text(encoding="utf-8")

    @as_tool(
        name="list_files",
        description="List files and directories under a directory relative to the documentation directory.",
    )
    def list_files(self, directory: str = ".") -> str:
        target = self._resolve_inside_base(directory)
        if target is None:
            return f"Error: directory path escapes base directory: {directory}"
        if not target.exists():
            return f"Error: directory does not exist: {target}"
        if not target.is_dir():
            return f"Error: {target} is not a directory"

        items = []
        for entry in sorted(target.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            items.append(f"  {entry.name}{suffix}")
        header = f"Contents of {directory}:"
        return header + "\n" + "\n".join(items) if items else header + "\n(empty)"
