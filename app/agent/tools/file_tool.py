from __future__ import annotations

from pathlib import Path

from app.agent.tools.base import BaseTool, as_tool


class FileTool(BaseTool):
    """File read/write tools scoped to a base directory."""

    name = "file"
    description = "File read/write tools scoped to a local documentation directory"

    def __init__(self, base_dir: str = "./docs"):
        self.base_dir = Path(base_dir).resolve()

    def _resolve_inside_base(self, file_path: str) -> Path | None:
        candidate = (self.base_dir / file_path).resolve()
        try:
            candidate.relative_to(self.base_dir)
        except ValueError:
            return None
        return candidate

    @as_tool(
        name="write_file",
        description="Write content to a file relative to the documentation directory.",
    )
    def write_file(self, file_path: str, content: str, append: bool = False) -> str:
        full_path = self._resolve_inside_base(file_path)
        if full_path is None:
            return f"Error: file path escapes base directory: {file_path}"
        full_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(full_path, mode, encoding="utf-8") as f:
            f.write(content)
        return f"File written: {full_path} ({len(content)} bytes)"

    @as_tool(
        name="read_file",
        description="Read a file relative to the documentation directory.",
    )
    def read_file(self, file_path: str) -> str:
        full_path = self._resolve_inside_base(file_path)
        if full_path is None:
            return f"Error: file path escapes base directory: {file_path}"
        if not full_path.exists():
            return f"Error: file does not exist: {full_path}"
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
        header = f"Contents of {target}:"
        return header + "\n" + "\n".join(items) if items else header + "\n(empty)"
