class FakeKV:
    def __init__(self):
        self.data = {}

    def get_by_id(self, key):
        return self.data.get(key)

    def upsert(self, values):
        self.data.update(values)

    def mset(self, values):
        self.data.update(values)

    def mdelete(self, keys):
        for key in keys:
            self.data.pop(key, None)

    def keys(self):
        return list(self.data.keys())


class FakeVDB:
    def __init__(self):
        self.items = {}
        self._id_to_meta = {}

    def add_texts(self, ids, texts, embeddings, metadatas):
        for item_id, text, metadata in zip(ids, texts, metadatas):
            self.items[item_id] = text
            self._id_to_meta[item_id] = {"text": text, "metadata": metadata}

    def delete_by_metadata(self, key, value):
        ids = [item_id for item_id, meta in self._id_to_meta.items() if meta["metadata"].get(key) == value]
        for item_id in ids:
            self.items.pop(item_id, None)
            self._id_to_meta.pop(item_id, None)

    def __len__(self):
        return len(self.items)


class FakeGraphStore:
    def __init__(self):
        self.nodes = {}
        self.edges = []

    def upsert_node(self, node_id, data):
        self.nodes[node_id] = data

    def upsert_edge(self, source, target, data):
        self.edges.append((source, target, data))

    def get_all_nodes(self):
        return list(self.nodes.items())

    def delete_node(self, node_id):
        self.nodes.pop(node_id, None)


class FakeStorageManager:
    def __init__(self):
        self.context = {
            "text_chunks_kv": FakeKV(),
            "chunks_vdb": FakeVDB(),
            "entities_vdb": FakeVDB(),
            "relationships_vdb": FakeVDB(),
            "graph": FakeGraphStore(),
        }
        self.finalized = False

    def get_context(self):
        return self.context

    async def finalize(self):
        self.finalized = True


class FakeRuntime:
    def __init__(self, storage_manager):
        self.storage_manager = storage_manager
        self.memory_manager = object()
        self.eval_manager = object()
        self.graph = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def install_runtime(monkeypatch, storage_manager):
    import app.cli as cli
    from rich.console import Console

    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(cli, "console", console)
    monkeypatch.setattr(cli, "AgentRuntime", lambda: FakeRuntime(storage_manager))
    return cli, console


def test_documents_ingest_reads_file_and_prints_summary(monkeypatch, tmp_path):
    storage_manager = FakeStorageManager()
    cli, console = install_runtime(monkeypatch, storage_manager)

    doc = tmp_path / "guide.md"
    doc.write_text("# 标题\n\n这是文档内容。", encoding="utf-8")

    monkeypatch.setattr(cli, "create_embeddings", lambda: type("Emb", (), {"embed_documents": lambda self, texts: [[0.1] for _ in texts]})())
    monkeypatch.setattr(cli, "extract_entities", lambda chunks: {"entities": [], "relationships": []})

    code = cli.main(["documents", "ingest", str(doc), "--id", "guide"])

    output = console.export_text()
    assert code == 0
    assert "ingested" in output
    assert "1" in output
    assert storage_manager.get_context()["text_chunks_kv"].get_by_id("doc_meta:guide") == {"source": str(doc)}
    assert storage_manager.finalized is True


def test_documents_stats_and_list_print_tables(monkeypatch):
    storage_manager = FakeStorageManager()
    ctx = storage_manager.get_context()
    ctx["text_chunks_kv"].upsert({"doc_meta:guide": {"source": "guide.md"}})
    ctx["text_chunks_kv"].mset({"chunk:guide_0": {"text": "内容", "doc_id": "guide"}})
    ctx["chunks_vdb"].add_texts(["guide_0"], ["内容"], [[0.1]], [{"doc_id": "guide", "chunk_index": 0}])
    cli, console = install_runtime(monkeypatch, storage_manager)

    assert cli.main(["documents", "stats"]) == 0
    assert cli.main(["documents", "list"]) == 0

    output = console.export_text()
    assert "total_documents" in output
    assert "guide" in output


def test_documents_delete_removes_document(monkeypatch):
    storage_manager = FakeStorageManager()
    ctx = storage_manager.get_context()
    ctx["text_chunks_kv"].upsert({"doc_meta:guide": {"source": "guide.md"}})
    ctx["text_chunks_kv"].mset({"chunk:guide_0": {"text": "内容", "doc_id": "guide"}})
    ctx["chunks_vdb"].add_texts(["guide_0"], ["内容"], [[0.1]], [{"doc_id": "guide", "chunk_index": 0}])
    cli, console = install_runtime(monkeypatch, storage_manager)

    code = cli.main(["documents", "delete", "guide", "--yes"])

    assert code == 0
    assert ctx["text_chunks_kv"].get_by_id("doc_meta:guide") is None
    assert len(ctx["chunks_vdb"]) == 0
    assert "deleted" in console.export_text()
