from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """工具基类，所有工具继承此类。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    def run(self, **kwargs) -> dict[str, Any]:
        """执行工具逻辑，返回结构化结果。"""


class ToolRegistry:
    """工具注册表，所有工具集中注册，Worker 通过名称获取。"""

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool:
        return cls._tools[name]

    @classmethod
    def get_all(cls) -> list[BaseTool]:
        return list(cls._tools.values())

    @classmethod
    def init_defaults(cls):
        """注册所有内置工具。"""
        from app.agent.tools.bash_tool import BashTool
        from app.agent.tools.code_tool import CodeTool
        from app.agent.tools.doc_tool import DocTool
        from app.agent.tools.search_tool import SearchTool
        cls.register(BashTool())
        cls.register(CodeTool())
        cls.register(DocTool())
        cls.register(SearchTool())
