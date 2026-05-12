import pytest

from app.agent.memory.memory_manager import MemoryManager


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[1.0] for _ in texts]


@pytest.mark.asyncio
async def test_store_session_memory_does_not_overwrite_previous_turns(tmp_path):
    manager = MemoryManager(str(tmp_path), embedding_dim=1)
    await manager.initialize()

    await manager.store_session_memory(
        user_id="alice",
        session_id="s1",
        memories=[{"type": "fact", "content": "第一条", "importance": 1.0}],
        embeddings_api=FakeEmbeddings(),
    )
    await manager.store_session_memory(
        user_id="alice",
        session_id="s1",
        memories=[{"type": "fact", "content": "第二条", "importance": 1.0}],
        embeddings_api=FakeEmbeddings(),
    )

    assert len(manager.core_memory_vdb) == 2
    texts = {meta["text"] for meta in manager.core_memory_vdb._id_to_meta.values()}
    assert texts == {"fact: 第一条", "fact: 第二条"}
    assert all(
        meta["metadata"]["session_id"] == "s1"
        for meta in manager.core_memory_vdb._id_to_meta.values()
    )
