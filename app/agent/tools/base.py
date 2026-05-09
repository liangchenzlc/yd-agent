from __future__ import annotations

import asyncio
import inspect
from typing import Any

from pydantic import create_model

# 全局 LangChain BaseTool 注册表（按工具名 -> StructuredTool）
_tool_registry: dict[str, Any] = {}


def as_tool(*, name: str | None = None, description: str | None = None):
    """将类方法标记为可调用工具。

    ``get_lc_tools()`` 会收集所有 @as_tool 标记的方法并创建 LangChain StructuredTool。
    """

    def decorator(func):
        func._tool_meta = {
            "name": name or func.__name__,
            "description": description or func.__doc__ or "",
        }
        return func

    return decorator


class BaseTool:
    """工具基类 — 按能力域组织多个 @as_tool 方法。"""

    name: str = ""
    description: str = ""

    def get_lc_tools(self) -> list:
        """收集 @as_tool 方法，创建 LangChain StructuredTool 并注册到全局 registry。"""
        if hasattr(self, "_lc_tools_cache"):
            return self._lc_tools_cache

        from langchain_core.tools import StructuredTool

        tools = []
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if not inspect.ismethod(attr) or not hasattr(attr, "_tool_meta"):
                continue

            meta = attr._tool_meta

            # 获取参数签名（排除 self）
            sig = inspect.signature(attr)
            params = [p for p in sig.parameters.values() if p.name != "self"]

            # 从类型注解构建 args_schema
            fields: dict[str, tuple] = {}
            for param in params:
                ann = param.annotation if param.annotation != inspect.Parameter.empty else str
                default = ... if param.default == inspect.Parameter.empty else param.default
                fields[param.name] = (ann, default)

            args_schema = create_model(f"{meta['name']}_args", **fields) if fields else None

            lc_tool = StructuredTool.from_function(
                name=meta["name"],
                description=meta["description"],
                func=attr,  # bound method, self 已绑定
                args_schema=args_schema,
            )

            _tool_registry[meta["name"]] = lc_tool
            tools.append(lc_tool)

        self._lc_tools_cache = tools
        return tools


class ToolRegistry:
    """工具注册表 — 管理 BaseTool 实例。"""

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool:
        return cls._tools[name]

    @classmethod
    def get_lc_tools(cls, tool_names: list[str]) -> list:
        """获取指定工具的 LangChain BaseTool 列表。"""
        tools = []
        for name in tool_names:
            inst = cls._tools.get(name)
            if inst is None:
                continue
            tools.extend(inst.get_lc_tools())
        return tools

    @classmethod
    def execute_tool(cls, tool_name: str, **kwargs) -> str:
        """按名称执行工具，返回文本结果供 LLM 使用。"""
        lc_tool = _tool_registry.get(tool_name)
        if lc_tool is None:
            return f"错误：未找到工具 '{tool_name}'"
        try:
            result = lc_tool.invoke(kwargs)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"工具 '{tool_name}' 执行失败: {e}"

    @classmethod
    async def aexecute_tool(cls, tool_name: str, **kwargs) -> str:
        """异步执行工具，通过线程池避免阻塞事件循环。"""
        lc_tool = _tool_registry.get(tool_name)
        if lc_tool is None:
            return f"错误：未找到工具 '{tool_name}'"
        try:
            result = await asyncio.to_thread(lc_tool.invoke, kwargs)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"工具 '{tool_name}' 执行失败: {e}"

    @classmethod
    def get_all(cls) -> list[BaseTool]:
        return list(cls._tools.values())

    @classmethod
    def init_defaults(cls):
        """注册所有内置工具（无依赖的默认实例）。"""
        from app.agent.tools.docker_sandbox_tool import DockerSandBoxTool
        from app.agent.tools.file_tool import FileTool
        from app.agent.tools.search_tool import SearchTool
        from app.agent.tools.bash_tool import BashTool

        cls.register(DockerSandBoxTool())
        cls.register(FileTool())
        cls.register(SearchTool())
        cls.register(BashTool())


# ---- ReAct 循环 ----

def react_loop(
    llm,
    prompt: str,
    tools: list,
    max_iterations: int = 5,
) -> str:
    """ReAct 循环：LLM 思考 → 调工具 → 回喂 → 直到 LLM 给出最终回答。"""
    from langchain_core.messages import HumanMessage, ToolMessage

    llm_with_tools = llm.bind_tools(tools)
    messages = [HumanMessage(content=prompt)]

    for _ in range(max_iterations):
        response = llm_with_tools.invoke(messages)

        if not response.tool_calls:
            return response.content

        # 一次 response 只 append 一次，避免重复插入同一条 AIMessage
        messages.append(response)
        for tc in response.tool_calls:
            result = ToolRegistry.execute_tool(tc["name"], **tc["args"])
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

    return response.content if hasattr(response, "content") else str(response)


async def areact_loop(
    llm,
    prompt: str,
    tools: list,
    max_iterations: int = 5,
) -> str:
    """异步 ReAct 循环。"""
    from langchain_core.messages import HumanMessage, ToolMessage

    llm_with_tools = llm.bind_tools(tools)
    messages = [HumanMessage(content=prompt)]

    for _ in range(max_iterations):
        response = await llm_with_tools.ainvoke(messages)

        if not response.tool_calls:
            return response.content

        messages.append(response)
        for tc in response.tool_calls:
            result = await ToolRegistry.aexecute_tool(tc["name"], **tc["args"])
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

    return response.content if hasattr(response, "content") else str(response)
