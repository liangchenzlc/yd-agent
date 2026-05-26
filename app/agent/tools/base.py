from __future__ import annotations

import asyncio
import inspect
from typing import Any

from pydantic import create_model

# 全局 LangChain BaseTool 注册表（按工具名 -> StructuredTool）
# 区别于 ToolRegistry（管理 BaseTool 实例），这个字典直接管理 LangChain 层级的工具，
# 供 react_loop / areact_loop 在运行时根据工具名快速查找并执行
_tool_registry: dict[str, Any] = {}


def as_tool(*, name: str | None = None, description: str | None = None):
    """将类方法标记为可调用工具。

    ``get_lc_tools()`` 会收集所有 @as_tool 标记的方法并创建 LangChain StructuredTool。
    设计意图：在一个 BaseTool 子类中组织多个相关的工具方法，而非为每个工具创建一个独立的类。
    """
    def decorator(func):
        func._tool_meta = {
            "name": name or func.__name__,
            "description": description or func.__doc__ or "",
        }
        return func

    return decorator


class BaseTool:
    """工具基类 — 按能力域组织多个 @as_tool 方法。

    典型用法：class SearchTool(BaseTool) 内部定义 search_web, search_news 等多个方法，
    每个方法用 @as_tool 装饰，get_lc_tools() 自动收集并创建 LangChain StructuredTool。
    """

    name: str = ""
    description: str = ""

    def get_lc_tools(self) -> list:
        """收集 @as_tool 方法，创建 LangChain StructuredTool 并注册到全局 registry。

        结果缓存到 _lc_tools_cache，避免重复调用 inspect 和 create_model
        （反射创建 Pydantic model 的开销不可忽略）。
        """
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

            # 从类型注解构建 Pydantic args_schema
            # 这是 StructuredTool.from_function 要求的：工具参数必须有 Schema 定义，
            # LLM 调用工具时根据 Schema 生成结构化的参数 JSON。
            # 注意：对于没有类型注解的参数，默认用 str；没有默认值的参数用 ...（required）。
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
    """工具注册表 — 管理 BaseTool 实例。

    职责分层：
    - ToolRegistry 管理 BaseTool 实例（业务层）
    - _tool_registry 管理 LangChain StructuredTool 实例（框架层）
    - BaseTool.get_lc_tools() 负责两者之间的转换
    """

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool:
        tool = cls._tools.get(name)
        if tool is None:
            registered = list(cls._tools.keys())
            raise KeyError(f"工具 '{name}' 未注册。已注册工具: {registered}")
        return tool

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
        """按名称执行工具，返回文本结果供 LLM 使用。

        返回 str 而非原始结果的原因：LLM 无法直接解析 Python 对象，
        必须序列化为文本。即使是工具执行异常也返回文本错误信息，
        让 LLM 可以据此决定下一步（重试、换策略或直接回复用户）。
        """
        lc_tool = _tool_registry.get(tool_name)
        if lc_tool is None:
            return f"错误：未找到工具 '{tool_name}'"
        try:
            result = lc_tool.invoke(kwargs)
            # None 结果仍需返回空字符串，否则后续 LLM 调用可能因 None 类型报错
            return str(result) if result is not None else ""
        except Exception as e:
            return f"工具 '{tool_name}' 执行失败（{e}）"

    @classmethod
    async def aexecute_tool(cls, tool_name: str, **kwargs) -> str:
        """异步执行工具，通过线程池避免阻塞事件循环。

        使用 asyncio.to_thread 是因为 LangChain StructuredTool.invoke 是同步方法，
        直接在异步上下文中调用会阻塞事件循环，影响其他并发任务（如同时处理多个 SSE 连接）。
        """
        lc_tool = _tool_registry.get(tool_name)
        if lc_tool is None:
            return f"错误：未找到工具 '{tool_name}'"
        try:
            result = await asyncio.to_thread(lc_tool.invoke, kwargs)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"工具 '{tool_name}' 执行失败（{e}）"

    @classmethod
    def get_all(cls) -> list[BaseTool]:
        return list(cls._tools.values())

    _initialized: bool = False

    @classmethod
    def init_defaults(cls):
        """注册所有内置工具（无依赖的默认实例），仅执行一次。

        使用 _initialized 标志确保幂等性：即使被多次调用也只初始化一次。
        所有工具在此集中注册，新增内置工具时只需在此 import 并 register。
        注意：需要外部依赖的工具（如需要数据库连接的）不应在此注册，
        应由调用方创建实例后自行 register。
        """
        if cls._initialized:
            return
        from app.agent.tools.database_tool import DatabaseTool
        from app.agent.tools.file_tool import FileTool
        from app.agent.tools.report_tool import ReportTool
        from app.agent.tools.search_tool import SearchTool

        cls.register(DatabaseTool())
        cls.register(FileTool())
        cls.register(ReportTool())
        cls.register(SearchTool())
        cls._initialized = True


# ---- ReAct 循环 ----

def react_loop(
    llm,
    prompt: str,
    tools: list,
    max_iterations: int = 5,
) -> str:
    """ReAct 循环：LLM 思考 → 调工具 → 回喂 → 直到 LLM 给出最终回答。

    max_iterations 是硬上限防止 infinite loop。每次迭代：
    1. LLM 决定调用工具或直接回答
    2. 如果返回 tool_calls，执行工具并将结果作为 ToolMessage 喂回
    3. 如果无 tool_calls，视为最终回答

    注意：langchain 的 bind_tools 要求 tools 是 BaseTool 列表，
    而非 ToolRegistry 中的实例。这里的 tools 应通过 ToolRegistry.get_lc_tools() 获取。
    """
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
            # 通过全局注册表执行而非直接调用 lc_tool，保持调用入口统一
            # ToolRegistry.execute_tool 负责异常处理、结果格式化、以及统一错误消息格式
            result = ToolRegistry.execute_tool(tc["name"], **tc["args"])
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

    # 超过 max_iterations 未得出最终答案时，返回最后一次 LLM 输出的内容
    # 即使不完整也比抛出异常好 —— 用户至少能看到部分结果
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
