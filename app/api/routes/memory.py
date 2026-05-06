from fastapi import APIRouter, HTTPException

from app.domain.schemas import MemoryItem, MemoryListResponse, MemoryDeleteResponse, ProfileResponse

router = APIRouter()


def _get_memory_manager():
    from app.main import get_memory_manager
    mgr = get_memory_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="记忆服务未就绪")
    return mgr


@router.get("/memory/{user_id}", response_model=MemoryListResponse)
async def get_user_memories(user_id: str):
    mgr = _get_memory_manager()

    core_memories = []
    for mem_id, meta in mgr.core_memory_vdb._id_to_meta.items():
        if meta.get("metadata", {}).get("user_id") == user_id:
            core_memories.append(MemoryItem(
                id=mem_id,
                type=meta.get("metadata", {}).get("type", ""),
                content=meta.get("text", ""),
                importance=meta.get("metadata", {}).get("importance", 0.0),
                timestamp=meta.get("metadata", {}).get("timestamp", ""),
            ))

    working_memories = []
    for mem_id, meta in mgr.working_memory_vdb._id_to_meta.items():
        if meta.get("metadata", {}).get("user_id") == user_id:
            working_memories.append(MemoryItem(
                id=mem_id,
                type=meta.get("metadata", {}).get("type", ""),
                content=meta.get("text", ""),
                importance=meta.get("metadata", {}).get("importance", 0.0),
                timestamp=meta.get("metadata", {}).get("timestamp", ""),
            ))

    return MemoryListResponse(
        user_id=user_id,
        core_memories=core_memories,
        working_memories=working_memories,
    )


@router.delete("/memory/{user_id}", response_model=MemoryDeleteResponse)
async def delete_user_memories(user_id: str):
    mgr = _get_memory_manager()
    await mgr.forget_user(user_id)
    return MemoryDeleteResponse(deleted=True, user_id=user_id)


@router.get("/profile/{user_id}", response_model=ProfileResponse)
async def get_user_profile(user_id: str):
    mgr = _get_memory_manager()
    profile = await mgr.get_user_profile(user_id)
    if profile is None or (not profile.get("topics") and not profile.get("recent_history") and profile.get("total_interactions", 0) == 0):
        pass  # 返回默认画像
    return ProfileResponse(
        user_id=user_id,
        topics=profile.get("topics", {}),
        total_interactions=profile.get("total_interactions", 0),
        last_active=profile.get("last_active", ""),
    )
