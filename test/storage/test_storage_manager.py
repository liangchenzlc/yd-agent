from app.agent.storage_manager import StorageManager


def test_has_documents_when_chunks_vector_store_has_data(tmp_path):
    manager = StorageManager(str(tmp_path), embedding_dim=4)
    manager.chunks_vdb.initialize()
    manager.text_chunks_kv.initialize()

    manager.chunks_vdb.add_texts(
        ["chunk_1"],
        ["stored chunk"],
        [[1.0, 0.0, 0.0, 0.0]],
        [{"doc_id": "doc_1"}],
    )

    assert manager.has_documents is True


def test_has_documents_when_only_doc_metadata_exists(tmp_path):
    manager = StorageManager(str(tmp_path), embedding_dim=4)
    manager.chunks_vdb.initialize()
    manager.text_chunks_kv.initialize()

    manager.text_chunks_kv.upsert({"doc_meta:doc_1": {"title": "Doc"}})

    assert manager.has_documents is True


def test_has_documents_false_for_empty_storage(tmp_path):
    manager = StorageManager(str(tmp_path), embedding_dim=4)
    manager.chunks_vdb.initialize()
    manager.text_chunks_kv.initialize()

    assert manager.has_documents is False
