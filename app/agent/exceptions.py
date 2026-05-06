class AgentError(Exception):
    """Agent 基础异常"""


class LLMError(AgentError):
    """LLM 调用失败"""


class SandboxError(AgentError):
    """Docker 沙箱执行失败"""


class WorkerError(AgentError):
    """Worker 执行失败"""


class RefinerError(AgentError):
    """Refiner 评估失败"""


class ActionError(AgentError):
    """Action Worker API 调用失败"""
