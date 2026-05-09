"""测试文档管理 API：摄入、统计、列出、删除（真实存储 + 真实 Embedding/LLM）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestIngestDocuments:
    """POST /documents/ingest"""

    def test_ingest_single_document(self, client):
        payload = {
            "documents": [
                {"id": "test_doc_1", "content": "人工智能是计算机科学的一个分支。机器学习是AI的一个子集。"}
            ]
        }
        resp = client.post("/documents/ingest", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ingested"] == 1
        assert data["total_chunks"] >= 1

    def test_ingest_multiple_documents(self, client):
        payload = {
            "documents": [
                {"id": "doc_a", "content": "Python是一种高级编程语言。"},
                {"id": "doc_b", "content": "FastAPI是一个现代Web框架。"},
            ]
        }
        resp = client.post("/documents/ingest", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ingested"] == 2

    def test_ingest_duplicate_document(self, client):
        payload = {"documents": [{"id": "dup_doc", "content": "重复文档。"}]}
        client.post("/documents/ingest", json=payload)
        resp = client.post("/documents/ingest", json=payload)
        assert resp.status_code == 200, resp.text
        assert resp.json()["skipped"] == 1

    def test_ingest_empty_content(self, client):
        resp = client.post("/documents/ingest", json={"documents": [{"id": "e", "content": ""}]})
        assert resp.status_code == 422

    def test_ingest_no_documents(self, client):
        resp = client.post("/documents/ingest", json={"documents": []})
        assert resp.status_code == 422


class TestDocumentStats:
    """GET /documents/stats"""

    def test_stats_empty(self, client):
        resp = client.get("/documents/stats")
        assert resp.status_code == 200, resp.text
        assert "total_documents" in resp.json()

    def test_stats_after_ingest(self, client):
        client.post("/documents/ingest", json={
            "documents": [{"id": "stats_test", "content": "测试文档。"}]
        })
        resp = client.get("/documents/stats")
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_documents"] > 0


class TestListDocuments:
    """GET /documents"""

    def test_list_documents(self, client):
        client.post("/documents/ingest", json={
            "documents": [{"id": "list_test", "content": "列表测试。"}]
        })
        resp = client.get("/documents")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json()["documents"], list)


class TestDeleteDocument:
    """DELETE /documents/{doc_id}"""

    def test_delete_document(self, client):
        client.post("/documents/ingest", json={
            "documents": [{"id": "delete_test", "content": "删除测试。"}]
        })
        resp = client.delete("/documents/delete_test")
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] is True
