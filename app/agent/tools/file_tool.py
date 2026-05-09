from __future__ import annotations

from pathlib import Path

from app.agent.tools.base import BaseTool, as_tool


class FileTool(BaseTool):
    """文件读写工具集，用于在本地文件系统中创建、读取和管理文件。"""

    name = "file"
    description = "文件读写工具集，用于在本地文件系统中创建、读取和管理文件"

    def __init__(self, base_dir: str = "./docs"):
        self.base_dir = Path(base_dir)

    @as_tool(
        name="write_file",
        description=(
            "将内容写入指定文件。如果文件所在的目录不存在会自动创建。"
            "append=True 时在文件末尾追加而不是覆盖。"
            "返回写入结果（文件路径和大小）。"
        ),
    )
    def write_file(self, file_path: str, content: str, append: bool = False) -> str:
        full_path = (self.base_dir / file_path).resolve()
        # 防止路径穿越到 base_dir 之外
        if not str(full_path).startswith(str(self.base_dir.resolve())):
            return f"错误：文件路径越界 {file_path}"
        full_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(full_path, mode, encoding="utf-8") as f:
            f.write(content)
        return f"文件已写入: {full_path} ({len(content)} 字节)"

    @as_tool(
        name="read_file",
        description="读取指定文件的全部内容并返回。文件路径相对于文档目录。",
    )
    def read_file(self, file_path: str) -> str:
        full_path = (self.base_dir / file_path).resolve()
        if not str(full_path).startswith(str(self.base_dir.resolve())):
            return f"错误：文件路径越界 {file_path}"
        if not full_path.exists():
            return f"错误：文件不存在 {full_path}"
        return full_path.read_text(encoding="utf-8")

    @as_tool(
        name="list_files",
        description="列出指定目录下的所有文件和子目录。directory 默认为根目录。",
    )
    def list_files(self, directory: str = ".") -> str:
        target = (self.base_dir / directory).resolve()
        if not str(target).startswith(str(self.base_dir.resolve())):
            return f"错误：目录路径越界 {directory}"
        if not target.exists():
            return f"错误：目录不存在 {target}"
        if not target.is_dir():
            return f"错误：{target} 不是目录"
        items = []
        for entry in sorted(target.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            items.append(f"  {entry.name}{suffix}")
        header = f"目录 {target} 的内容:"
        return header + "\n" + "\n".join(items) if items else header + "（空）"
