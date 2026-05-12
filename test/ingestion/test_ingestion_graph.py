from app.agent.ingestion.ingestion_graph import check_duplicates_node


class FakeKV:
    def __init__(self, keys=None):
        self.data = {key: {} for key in keys or []}

    def get_by_id(self, key):
        return self.data.get(key)


class FakeStorage:
    def __init__(self, keys=None):
        self.text_chunks_kv = FakeKV(keys)


def test_check_duplicates_uses_doc_meta_key_and_clears_previous_document_state():
    storage = FakeStorage(keys=["doc_meta:900150983cd24fb0"])
    node = check_duplicates_node(storage)

    result = node(
        {
            "documents": [{"content": "abc", "metadata": {}}],
            "current_index": 0,
            "chunks": [{"content": "previous"}],
            "entities": [{"name": "previous"}],
            "relationships": [{"source": "previous"}],
        }
    )

    assert result["is_duplicate"] is True
    assert result["chunks"] == []
    assert result["entities"] == []
    assert result["relationships"] == []
