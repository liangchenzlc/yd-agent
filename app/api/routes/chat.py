import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.domain.schemas import ChatRequest, ChatResponse, WorkerResultItem
from app.agent.state import AgentState
from app.agent.graph import build_agent_graph

from app.agent.storage_manager import StorageManager
from app.agent.memory.memory_manager import MemoryManager

router = APIRouter()

_agent_graph = None


def get_graph(
    storage_manager: StorageManager | None = None,
    memory_manager: MemoryManager | None = None,
):
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph(
            storage_manager=storage_manager,
            memory_manager=memory_manager,
        )
    return _agent_graph


def _initial_state(req: ChatRequest) -> AgentState:
    return AgentState(
        messages=[HumanMessage(content=req.message)],
        worker_assignments=[],
        dispatch_reasoning="",
        worker_results=[],
        refinement_count=0,
        refinement_needed=False,
        refinement_feedback="",
        refinement_targets=[],
        final_answer="",
        user_id=req.user_id,
        user_profile={},
        relevant_memories=[],
        session_history=[],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    graph = get_graph()
    state = _initial_state(req)

    try:
        result = await graph.ainvoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}")

    worker_results = [
        WorkerResultItem(
            worker=r.get("worker", "?"),
            content=r.get("content", ""),
            error=r.get("error"),
            metadata=r.get("metadata", {}),
        )
        for r in result.get("worker_results", [])
    ]

    # 异步触发后台评估
    _trigger_eval(req, result, worker_results)

    return ChatResponse(
        answer=result.get("final_answer", ""),
        reasoning=result.get("dispatch_reasoning", ""),
        workers_used=result.get("worker_assignments", []),
        worker_results=worker_results,
        refinements=result.get("refinement_count", 0),
        session_id=req.session_id,
        memories_updated=result.get("memories_updated", False),
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    graph = get_graph()
    state = _initial_state(req)

    async def event_generator():
        final_answer = ""
        workers_used: list[str] = []
        worker_results_list: list[dict] = []
        refinement_count = 0
        try:
            async for chunk in graph.astream(state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if node_name == "supervisor":
                        workers_used = node_output.get("worker_assignments", [])
                        yield f"data: {json.dumps({'type': 'supervisor', 'reasoning': node_output.get('dispatch_reasoning', ''), 'workers': workers_used})}\n\n"

                    elif node_name == "summary_worker":
                        final_answer = node_output.get("final_answer", "")
                        if final_answer:
                            yield f"data: {json.dumps({'type': 'summary_chunk', 'content': final_answer})}\n\n"

                    elif node_name == "refiner":
                        refinement_needed = node_output.get("refinement_needed", False)
                        refinement_count = node_output.get("refinement_count", refinement_count)
                        yield f"data: {json.dumps({'type': 'refiner', 'score': 7 if not refinement_needed else 5, 'passed': not refinement_needed})}\n\n"

                    elif node_name in ("retrieval_worker", "code_worker", "docs_worker"):
                        for r in node_output.get("worker_results", []):
                            worker_results_list.append(r)
                            yield f"data: {json.dumps({'type': 'worker_start', 'worker': r.get('worker', node_name)})}\n\n"
                            yield f"data: {json.dumps({'type': 'worker_end', 'worker': r.get('worker', node_name), 'result': {'content': r.get('content', ''), 'error': r.get('error')}})}\n\n"

            # 触发后台评估 (fire-and-forget, 不阻塞流)
            if final_answer:
                _trigger_eval(
                    req,
                    {"final_answer": final_answer, "worker_results": worker_results_list, "refinement_count": refinement_count},
                    worker_results_list,
                )

            # 最终状态（必须在 eval 之后发送以确保 done 是最后一个事件）
            yield f"data: {json.dumps({'type': 'done', 'workers_used': workers_used, 'refinements': refinement_count, 'session_id': req.session_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _trigger_eval(req: ChatRequest, result: dict, worker_results: list) -> asyncio.Task | None:
    """Fire-and-forget 触发后台评估。"""
    from app.config.settings import get_settings
    from app.main import get_eval_manager
    from app.agent.eval.evaluator import run_evaluation

    settings = get_settings()
    if not settings.eval_enabled:
        return None

    eval_mgr = get_eval_manager()
    if eval_mgr is None:
        return None

    return asyncio.create_task(
        run_evaluation(
            user_id=req.user_id,
            session_id=req.session_id,
            message=req.message,
            final_answer=result.get("final_answer", ""),
            worker_results=[
                {
                    "worker": r.worker if hasattr(r, "worker") else r.get("worker", ""),
                    "content": r.content if hasattr(r, "content") else r.get("content", ""),
                    "error": r.error if hasattr(r, "error") else r.get("error"),
                    "metadata": r.metadata if hasattr(r, "metadata") else r.get("metadata", {}),
                }
                for r in worker_results
            ],
            refinement_count=result.get("refinement_count", 0),
            eval_manager=eval_mgr,
            hard_case_threshold=settings.eval_hard_case_threshold,
            golden_model=settings.eval_golden_model or None,
        )
    )
