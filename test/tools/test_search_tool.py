"""测试 SearchTool（真实知识库检索）。"""

from app.agent.tools.search_tool import SearchTool


def test_search_no_storage_manager():
    """无 storage_manager 时直接返回无文档提示（不调用 LLM）。"""
    tool = SearchTool(storage_manager=None)
    result = tool.search("测试查询")
    assert "没有已摄入的文档" in result


def test_search_empty_context():
    """空 storage_manager 时返回无文档提示。"""
    tool = SearchTool(storage_manager=None)
    result = tool.search("")
    assert "没有已摄入的文档" in result


def test_set_storage_manager_to_none():
    """set_storage_manager(None) 后 search 返回无文档提示。"""
    tool = SearchTool(storage_manager=None)
    tool.set_storage_manager(None)
    assert tool.storage_manager is None
    result = tool.search("test")
    assert "没有已摄入的文档" in result
