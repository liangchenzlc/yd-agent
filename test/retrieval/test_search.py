from app.agent.retrieval import search


class FakeVDB:
    def __init__(self, score=0.42):
        self.calls = []
        self.score = score

    def is_empty(self):
        return False

    def similarity_search_by_vector(self, embedding, k=10, score_threshold=0.6):
        self.calls.append({"embedding": embedding, "k": k, "score_threshold": score_threshold})
        if score_threshold is not None and self.score < score_threshold:
            return []
        return [{"text": "试用期 3-6 个月", "score": self.score, "metadata": {}}]


def test_search_by_vector_uses_low_confidence_threshold(monkeypatch):
    monkeypatch.setattr(search, "_compute_embeddings", lambda texts: [[0.1, 0.2]])
    vdb = FakeVDB()

    results = search.search_by_vector("入职试用期多长", vdb)

    assert results == [{"text": "试用期 3-6 个月", "score": 0.42, "metadata": {}}]
    assert vdb.calls[0]["score_threshold"] == search.LOW_CONFIDENCE_THRESHOLD


def test_local_search_uses_low_confidence_threshold(monkeypatch):
    monkeypatch.setattr(search, "_compute_embeddings", lambda texts: [[0.1, 0.2]])
    vdb = FakeVDB()

    results = search.local_search(["试用期"], vdb)

    assert results["entities"] == [{"text": "试用期 3-6 个月", "score": 0.42, "metadata": {}}]
    assert vdb.calls[0]["score_threshold"] == search.LOW_CONFIDENCE_THRESHOLD


def test_search_by_vector_falls_back_to_one_low_confidence_result(monkeypatch):
    monkeypatch.setattr(search, "_compute_embeddings", lambda texts: [[0.1, 0.2]])
    vdb = FakeVDB(score=0.1)

    results = search.search_by_vector("完全不相关的问题", vdb)

    assert len(results) == 1
    assert results[0]["metadata"]["low_confidence"] is True
    assert vdb.calls == [
        {"embedding": [0.1, 0.2], "k": 10, "score_threshold": search.LOW_CONFIDENCE_THRESHOLD},
        {"embedding": [0.1, 0.2], "k": 1, "score_threshold": None},
    ]
