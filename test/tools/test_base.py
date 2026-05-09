"""测试 @as_tool 装饰器、BaseTool、ToolRegistry（纯本地测试，无需 LLM）。"""

from app.agent.tools import BaseTool, ToolRegistry, as_tool


class _GreetTool(BaseTool):
    name = "greet_tool"
    description = "Greet tool for testing"

    @as_tool(name="greet", description="Say hello to someone")
    def greet(self, name: str = "world") -> str:
        return f"Hello, {name}!"

    @as_tool(name="add", description="Add two numbers")
    def add(self, a: int, b: int = 0) -> int:
        return a + b


class _ErrorTool(BaseTool):
    name = "error_tool"
    description = "Error tool"

    @as_tool(name="fail", description="Always fails")
    def fail(self) -> str:
        raise ValueError("intentional error")


# ─── @as_tool ────────────────────────────────────────────────


def test_as_tool_sets_metadata():
    assert hasattr(_GreetTool.greet, "_tool_meta")
    assert _GreetTool.greet._tool_meta["name"] == "greet"
    assert _GreetTool.greet._tool_meta["description"] == "Say hello to someone"


def test_as_tool_default_name_from_func():
    assert _GreetTool.add._tool_meta["name"] == "add"


# ─── BaseTool.get_lc_tools ───────────────────────────────────


def test_get_lc_tools_returns_structured_tools():
    tool = _GreetTool()
    lc_tools = tool.get_lc_tools()
    assert len(lc_tools) == 2
    names = [t.name for t in lc_tools]
    assert "greet" in names
    assert "add" in names


def test_get_lc_tools_caching():
    tool = _GreetTool()
    first = tool.get_lc_tools()
    second = tool.get_lc_tools()
    assert first is second


# ─── ToolRegistry ────────────────────────────────────────────


def test_tool_registry_register_and_get():
    tool = _GreetTool()
    ToolRegistry.register(tool)
    assert ToolRegistry.get("greet_tool") is tool


def test_tool_registry_get_all():
    tool = _ErrorTool()
    ToolRegistry.register(tool)
    all_tools = ToolRegistry.get_all()
    assert any(t.name == "error_tool" for t in all_tools)


def test_tool_registry_get_lc_tools():
    tool = _GreetTool()
    ToolRegistry.register(tool)
    tools = ToolRegistry.get_lc_tools(["greet_tool"])
    assert len(tools) == 2


def test_tool_registry_get_lc_tools_skip_missing():
    tools = ToolRegistry.get_lc_tools(["nonexistent"])
    assert tools == []


def test_tool_registry_execute_tool():
    tool = _GreetTool()
    tool.get_lc_tools()
    result = ToolRegistry.execute_tool("greet", name="测试")
    assert "Hello, 测试" in result


def test_tool_registry_execute_tool_not_found():
    result = ToolRegistry.execute_tool("nonexistent")
    assert "未找到" in result


def test_tool_registry_execute_tool_exception():
    tool = _ErrorTool()
    tool.get_lc_tools()
    result = ToolRegistry.execute_tool("fail")
    assert "执行失败" in result
    assert "intentional error" in result


def test_tool_registry_init_defaults():
    ToolRegistry.init_defaults()
    for name in ("docker_sandbox", "file", "search", "bash"):
        assert ToolRegistry.get(name) is not None
