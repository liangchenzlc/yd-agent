"""共享测试辅助函数（无 mock，全真实依赖）。"""

import subprocess
import sys

from langchain_core.messages import HumanMessage

from app.agent.state import AgentState


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
        session_id="test",
        user_profile={},
        relevant_memories=[],
        session_history=[],
    )


def docker_available() -> bool:
    """检查 Docker 是否可用。"""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def skip_if_no_docker():
    """如果 Docker 不可用则跳过测试。"""
    if not docker_available():
        import pytest
        pytest.skip("Docker 不可用，跳过测试")
