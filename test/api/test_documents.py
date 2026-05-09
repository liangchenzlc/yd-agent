"""测试文档管理 API：摄入、统计、列出、删除。"""

from unittest import mock

import pytest

from app.agent.storage_manager import StorageManager
from test.conftest import FakeEmbeddings


@pytest.fixture
def mgr():
    return StorageManager("/tmp/yd-agent-test", embedding_dim=128)


@pytest.fixture
def mock_deps(mgr):
    """Mock 文档 API 依赖的所有外部调用（存储、LLM、Embedding）。"""
    from test.mock_utils import FakeLLM

    mock_llm = FakeLLM()
    with (
        mock.patch("app.main.get_storage_manager", return_value=mgr),
        mock.patch("app.api.routes.documents.create_embeddings", return_value=FakeEmbeddings()),
        # extract_entities 中模块级 import create_llm，需 patch 其引用
        mock.patch("app.agent.llm.factory.create_llm", return_value=mock_llm),
    ):
        yield


@pytest.fixture
def client(mock_deps):
    from app.main import create_app
    from fastapi.testclient import TestClient
    return TestClient(create_app())


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
