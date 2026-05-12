from app.agent.retrieval.chunk_picker import collect_chunks_from_entities


class FakeKV:
    def __init__(self, data):
        self.data = data

    def get_by_id(self, key):
        return self.data.get(key)


def test_collect_chunks_from_entities_supports_doc_prefixed_chunk_keys():
    store = FakeKV(
        {
            "chunk:doc_1_chunk_000000": {
                "text": "试用期 3-6 个月",
                "doc_id": "doc_1",
            }
        }
    )
    entities = [
        {
            "metadata": {
                "doc_id": "doc_1",
                "source_id": "chunk_000000",
            }
        }
    ]

    chunks = collect_chunks_from_entities(entities, store)

    assert chunks == [{"text": "试用期 3-6 个月", "doc_id": "doc_1"}]


def test_collect_chunks_from_entities_keeps_legacy_chunk_keys():
    store = FakeKV({"chunk:chunk_000000": {"text": "legacy chunk"}})
    entities = [{"metadata": {"source_id": "chunk_000000"}}]

    chunks = collect_chunks_from_entities(entities, store)

    assert chunks == [{"text": "legacy chunk"}]
