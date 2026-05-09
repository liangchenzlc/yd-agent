"""共享 mock 工具：用于模拟 LLM、Docker 沙箱等外部依赖。"""
import json
from typing import Any

from app.agent.state import AgentState
from app.agent.sandbox.docker_sandbox import SandboxResult
from langchain_core.messages import HumanMessage

# 预设 LLM 响应
SUPERVISOR_SUMMARY_JSON = '{"workers": ["summary"], "reasoning": "简单对话"}'
SUPERVISOR_CODE_JSON = '{"workers": ["code"], "reasoning": "需要代码执行"}'
SUPERVISOR_RETRIEVAL_JSON = '{"workers": ["retrieval"], "reasoning": "需要检索知识"}'
SUPERVISOR_DOCS_JSON = '{"workers": ["docs"], "reasoning": "需要编写文档"}'
REFINER_PASS_JSON = '{"score": 9, "faithfulness": true, "relevance": true, "completeness": true, "feedback": "", "retarget_workers": []}'
CODE_OUTPUT = '```python\nprint("Hello from code worker")\n```'
DEFAULT_ANSWER = "这是一个模拟的回答。"
MEMORY_EXTRACT_JSON = '{"memories": [{"type": "fact", "content": "用户是后端工程师", "importance": 0.9, "category": "role"}]}'
EVAL_PASS_JSON = '{"faithfulness": {"score": 8, "passed": true, "feedback": ""}, "relevance": {"score": 8, "passed": true, "feedback": ""}, "completeness": {"score": 7, "passed": true, "feedback": ""}, "overall_score": 8, "is_hard_case": false, "summary": "回答质量良好。"}'
KEYWORDS_JSON = '{"ll_keywords": ["python", "code"], "hl_keywords": ["programming", "development"]}'


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeStructuredLLM:
    """模拟 with_structured_output，通过父 FakeLLM 的共享响应队列获取文本再解析为模型。"""

    def __init__(self, parent_fake: "FakeLLM", schema: type):
        self._parent = parent_fake
        self._schema = schema

    def _parse(self, text: str) -> Any:
        try:
            import json_repair
            data = json.loads(text) if text.startswith("{") else json_repair.loads(text)
            return self._schema(**data) if isinstance(data, dict) else self._schema()
        except Exception:
            return self._schema()

    def invoke(self, prompt: str | list) -> Any:
        # 通过父 FakeLLM 的 invoke 获取文本，与直接 invoke 共享响应队列和计数器
        resp = self._parent.invoke(prompt)
        return self._parse(resp.content)

    async def ainvoke(self, prompt: str | list) -> Any:
        return self.invoke(prompt)


class FakeLLM:
    """模拟 LLM，支持预设响应以及 with_structured_output。"""

    def __init__(self, responses: str | list[str | None] | list[str] | None = None):
        if isinstance(responses, str) or responses is None:
            self._responses = [responses]
        else:
            self._responses = list(responses)
        self._call_count = 0

    def with_structured_output(self, schema, **kwargs) -> _FakeStructuredLLM:
        return _FakeStructuredLLM(self, schema)

    async def ainvoke(self, prompt: str | list):
        return self.invoke(prompt)

    def invoke(self, prompt: str | list):
        idx = self._call_count
        self._call_count += 1

        if idx < len(self._responses) and self._responses[idx] is not None:
            return _FakeResponse(self._responses[idx])

        text = prompt if isinstance(prompt, str) else " ".join(
            m.get("content", "") if isinstance(m, dict) else str(m) for m in prompt
        )

        return _FakeResponse(self._fallback(text))

    def _fallback(self, prompt: str) -> str:
        if "Python 代码" in prompt and "用户需求" in prompt:
            return CODE_OUTPUT
        return DEFAULT_ANSWER


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
