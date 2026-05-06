"""共享 mock 工具：用于模拟 LLM、Docker 沙箱、httpx 等外部依赖。"""

from app.agent.state import AgentState
from app.agent.sandbox.docker_sandbox import SandboxResult
from langchain_core.messages import HumanMessage

# 预设 LLM 响应
SUPERVISOR_SUMMARY_JSON = '```json\n{"workers": ["summary"], "reasoning": "简单对话"}\n```'
SUPERVISOR_CODE_JSON = '```json\n{"workers": ["code"], "reasoning": "需要代码执行"}\n```'
SUPERVISOR_RETRIEVAL_JSON = '```json\n{"workers": ["retrieval"], "reasoning": "需要检索知识"}\n```'
REFINER_PASS_JSON = '```json\n{"score": 9, "faithfulness": true, "relevance": true, "completeness": true, "feedback": "", "retarget_workers": []}\n```'
CODE_OUTPUT = '```python\nprint("Hello from code worker")\n```'
DEFAULT_ANSWER = "这是一个模拟的回答。"


class FakeLLM:
    """模拟 LLM，支持预设响应或按顺序返回多个响应。"""

    def __init__(self, responses: str | list[str] | None = None):
        if isinstance(responses, str) or responses is None:
            self._responses = [responses]
        else:
            self._responses = list(responses)
        self._call_count = 0

    async def ainvoke(self, prompt: str | list):
        return self.invoke(prompt)

    def invoke(self, prompt: str | list):
        idx = self._call_count
        self._call_count += 1

        if idx < len(self._responses) and self._responses[idx] is not None:
            return _FakeResponse(self._responses[idx])

        # 提取文本用于 fallback 判断
        text = prompt
        if isinstance(prompt, list):
            text = " ".join(m.get("content", "") if isinstance(m, dict) else str(m) for m in prompt)

        return _FakeResponse(self._fallback(text))

    def _fallback(self, prompt: str) -> str:
        if "score" in prompt and "faithfulness" in prompt:
            return REFINER_PASS_JSON
        if "实体" in prompt and "关系" in prompt:
            return '```json\n{"entities": [{"name": "AI", "type": "concept", "description": "人工智能"}], "relationships": []}\n```'
        if "Python 代码" in prompt and "用户需求" in prompt:
            return CODE_OUTPUT
        if "API 调用" in prompt and "method" in prompt:
            return '```json\n{"method": "GET", "url": "https://httpbin.org/get", "headers": {}, "body": null}\n```'
        return DEFAULT_ANSWER


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


def fake_run_code(code: str, timeout: int | None = None) -> SandboxResult:
    """模拟 Docker 沙箱，返回成功结果。"""
    return SandboxResult(stdout="mock output", stderr="", exit_code=0, timed_out=False)


def fake_run_code_error(code: str, timeout: int | None = None) -> SandboxResult:
    """模拟 Docker 沙箱，返回错误结果。"""
    return SandboxResult(stdout="", stderr="NameError: name 'x' is not defined", exit_code=1, timed_out=False)


def make_initial_state(message: str, user_id: str = "default") -> AgentState:
    """创建一个初始 AgentState 用于测试。"""
    return AgentState(
        messages=[HumanMessage(content=message)],
        worker_assignments=[],
        dispatch_reasoning="",
        worker_results=[],
        refinement_count=0,
        refinement_needed=False,
        refinement_feedback="",
        refinement_targets=[],
        final_answer="",
        user_id=user_id,
        user_profile={},
        relevant_memories=[],
        session_history=[],
    )
