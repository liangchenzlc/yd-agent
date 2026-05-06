import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.domain.schemas import ChatRequest, ChatResponse, WorkerResultItem
from app.agent.state import AgentState
from app.agent.graph import build_agent_graph

router = APIRouter()

_agent_graph = None


def get_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
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

    return ChatResponse(
        answer=result.get("final_answer", ""),
        reasoning=result.get("dispatch_reasoning", ""),
        workers_used=result.get("worker_assignments", []),
        worker_results=worker_results,
        refinements=result.get("refinement_count", 0),
        session_id=req.session_id,
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    graph = get_graph()
    state = _initial_state(req)

    async def event_generator():
        try:
            async for chunk in graph.astream(state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if node_name == "supervisor":
                        yield f"data: {json.dumps({'type': 'supervisor', 'reasoning': node_output.get('dispatch_reasoning', ''), 'workers': node_output.get('worker_assignments', [])})}\n\n"

                    elif node_name == "summary_worker":
                        answer = node_output.get("final_answer", "")
                        if answer:
                            yield f"data: {json.dumps({'type': 'summary_chunk', 'content': answer})}\n\n"

                    elif node_name == "refiner":
                        yield f"data: {json.dumps({'type': 'refiner', 'score': 7 if not node_output.get('refinement_needed') else 5, 'passed': not node_output.get('refinement_needed', False)})}\n\n"

                    elif node_name in ("retrieval_worker", "code_worker", "action_worker"):
                        for r in node_output.get("worker_results", []):
                            yield f"data: {json.dumps({'type': 'worker_start', 'worker': r.get('worker', node_name)})}\n\n"
                            yield f"data: {json.dumps({'type': 'worker_end', 'worker': r.get('worker', node_name), 'result': {'content': r.get('content', ''), 'error': r.get('error')}})}\n\n"

            # 最终状态
            yield f"data: {json.dumps({'type': 'done', 'workers_used': [], 'refinements': 0, 'session_id': req.session_id})}\n\n"

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
