"""测试 FileTool（读写文件、路径穿越防护）。"""

from app.agent.tools.file_tool import FileTool


def test_write_and_read_file(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.write_file("hello.txt", "Hello, world!")
    assert "文件已写入" in result

    content = tool.read_file("hello.txt")
    assert content == "Hello, world!"


def test_write_file_creates_subdirectories(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.write_file("sub/deep/file.txt", "deep content")
    assert "文件已写入" in result
    assert (tmp_path / "sub" / "deep" / "file.txt").exists()


def test_write_file_append(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    tool.write_file("log.txt", "line1\n")
    tool.write_file("log.txt", "line2\n", append=True)
    content = tool.read_file("log.txt")
    assert content == "line1\nline2\n"


def test_read_file_not_found(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.read_file("nonexistent.txt")
    assert "错误：文件不存在" in result


def test_list_files(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("c")

    tool = FileTool(base_dir=str(tmp_path))
    result = tool.list_files(".")
    assert "a.txt" in result
    assert "b.txt" in result
    assert "sub/" in result or "sub" in result


def test_list_files_empty_directory(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.list_files(".")
    assert "（空）" in result


def test_list_files_nonexistent(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.list_files("no_such_dir")
    assert "错误：目录不存在" in result


def test_list_files_path_is_file(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.list_files("file.txt")
    assert "不是目录" in result


def test_path_traversal_write_blocked(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.write_file("../../outside.txt", "evil")
    assert "路径越界" in result
    assert not (tmp_path / ".." / "outside.txt").resolve().exists()


def test_path_traversal_read_blocked(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.read_file("../../etc/passwd")
    assert "路径越界" in result


def test_path_traversal_list_blocked(tmp_path):
    tool = FileTool(base_dir=str(tmp_path))
    result = tool.list_files("../../etc")
    assert "路径越界" in result
