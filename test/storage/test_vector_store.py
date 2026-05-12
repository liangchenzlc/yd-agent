import numpy as np

from app.agent.storage.vector_store import FAISSStore


def test_delete_rebuilds_index_and_keeps_remaining_searchable(tmp_path):
    store = FAISSStore("test", str(tmp_path), embedding_dim=4)
    store.initialize()

    emb_a = np.array([1.0, 0.0, 0.0, 0.0]).tolist()
    emb_b = np.array([0.0, 1.0, 0.0, 0.0]).tolist()
    store.add_texts(
        ["a", "b"],
        ["alpha", "beta"],
        [emb_a, emb_b],
        [{"doc_id": "doc_a"}, {"doc_id": "doc_b"}],
    )

    store.delete(["a"])

    assert len(store) == 1
    assert not store.is_empty()
    results = store.similarity_search_by_vector(emb_b, k=5, score_threshold=0.0)
    assert [r["id"] for r in results] == ["b"]


def test_delete_by_metadata_removes_matching_items(tmp_path):
    store = FAISSStore("test", str(tmp_path), embedding_dim=4)
    store.initialize()

    store.add_texts(
        ["a", "b"],
        ["alpha", "beta"],
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
        [{"doc_id": "same"}, {"doc_id": "other"}],
    )

    deleted = store.delete_by_metadata("doc_id", "same")

    assert deleted == ["a"]
    assert list(store._id_to_meta.keys()) == ["b"]


def test_add_texts_replaces_existing_id_without_orphan_vector(tmp_path):
    store = FAISSStore("test", str(tmp_path), embedding_dim=4)
    store.initialize()

    old_embedding = [1.0, 0.0, 0.0, 0.0]
    new_embedding = [0.0, 1.0, 0.0, 0.0]

    store.add_texts(["same"], ["old text"], [old_embedding], [{"version": "old"}])
    store.add_texts(["same"], ["new text"], [new_embedding], [{"version": "new"}])

    assert len(store) == 1
    assert store.index.ntotal == 1

    old_results = store.similarity_search_by_vector(old_embedding, k=5, score_threshold=0.1)
    assert old_results == []

    new_results = store.similarity_search_by_vector(new_embedding, k=5, score_threshold=0.0)
    assert len(new_results) == 1
    assert new_results[0]["id"] == "same"
    assert new_results[0]["text"] == "new text"
    assert new_results[0]["metadata"] == {"version": "new"}
    assert new_results[0]["score"] == 1.0
