from fastapi import APIRouter, HTTPException, Query

from app.domain.schemas import (
    EvalRunItem, EvalRunResponse,
    HardCaseItem, HardCaseListResponse,
    EvalSummaryResponse,
    FeedbackRequest, FeedbackItem, FeedbackListResponse,
)

router = APIRouter()


def _get_eval_manager():
    from app.main import get_eval_manager
    mgr = get_eval_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="评估服务未就绪")
    return mgr


# ---- 评估摘要 ----

@router.get("/eval/summary", response_model=EvalSummaryResponse)
async def get_eval_summary():
    mgr = _get_eval_manager()
    summary = await mgr.get_eval_summary()
    return EvalSummaryResponse(**summary)


# ---- 评估运行记录 ----

@router.get("/eval/runs", response_model=EvalRunResponse)
async def list_eval_runs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_score: int = Query(0, ge=0, le=10),
    max_score: int = Query(10, ge=0, le=10),
):
    mgr = _get_eval_manager()
    runs = await mgr.list_eval_runs(limit=limit, offset=offset, min_score=min_score, max_score=max_score)
    total = await mgr.count_eval_runs(min_score=min_score, max_score=max_score)
    return EvalRunResponse(
        runs=[EvalRunItem(**r) for r in runs],
        total=total,
    )


@router.get("/eval/runs/{run_id}", response_model=EvalRunItem)
async def get_eval_run(run_id: str):
    mgr = _get_eval_manager()
    run = await mgr.get_eval_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"评估记录 {run_id} 不存在")
    return EvalRunItem(**run)


@router.delete("/eval/runs")
async def delete_eval_runs():
    mgr = _get_eval_manager()
    count = await mgr.delete_eval_runs()
    return {"deleted": True, "count": count}


# ---- 难例 ----

@router.get("/eval/hard-cases", response_model=HardCaseListResponse)
async def list_hard_cases(
    reviewed: bool | None = Query(None, description="按审核状态过滤：true=已审核，false=未审核，不传=全部"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    mgr = _get_eval_manager()
    cases = await mgr.list_hard_cases(reviewed=reviewed, limit=limit, offset=offset)
    total = await mgr.count_hard_cases(reviewed=reviewed)
    return HardCaseListResponse(
        cases=[HardCaseItem(**c) for c in cases],
        total=total,
    )


@router.get("/eval/hard-cases/{case_id}", response_model=HardCaseItem)
async def get_hard_case(case_id: str):
    mgr = _get_eval_manager()
    case = await mgr.get_hard_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"难例 {case_id} 不存在")
    return HardCaseItem(**case)


@router.patch("/eval/hard-cases/{case_id}/review", response_model=HardCaseItem)
async def mark_hard_case_reviewed(case_id: str):
    mgr = _get_eval_manager()
    ok = await mgr.mark_case_reviewed(case_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"难例 {case_id} 不存在")
    case = await mgr.get_hard_case(case_id)
    return HardCaseItem(**case)


@router.delete("/eval/hard-cases")
async def delete_hard_cases():
    mgr = _get_eval_manager()
    count = await mgr.delete_hard_cases()
    return {"deleted": True, "count": count}


# ---- 用户反馈 ----

@router.post("/feedback", response_model=FeedbackItem)
async def submit_feedback(req: FeedbackRequest):
    mgr = _get_eval_manager()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    fid = await mgr.add_feedback({
        "user_id": req.user_id,
        "session_id": req.session_id,
        "thumbs_up": req.thumbs_up,
        "comment": req.comment,
        "message": req.message,
        "answer": req.answer,
        "timestamp": now.isoformat(),
    })
    return FeedbackItem(
        feedback_id=fid,
        user_id=req.user_id,
        session_id=req.session_id,
        thumbs_up=req.thumbs_up,
        comment=req.comment,
        message=req.message,
        answer=req.answer,
        timestamp=now.isoformat(),
    )


@router.get("/feedback", response_model=FeedbackListResponse)
async def list_feedback(
    user_id: str | None = Query(None, description="按用户过滤，不传则返回全部"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    mgr = _get_eval_manager()
    items = await mgr.list_feedback(user_id=user_id, limit=limit, offset=offset)
    total = await mgr.count_feedback(user_id=user_id)
    stats = await mgr.get_feedback_stats()
    return FeedbackListResponse(
        feedback=[FeedbackItem(**f) for f in items],
        total=total,
        thumbs_up_count=stats["thumbs_up"],
        thumbs_down_count=stats["thumbs_down"],
    )


@router.get("/feedback/stats")
async def get_feedback_stats():
    mgr = _get_eval_manager()
    return await mgr.get_feedback_stats()
