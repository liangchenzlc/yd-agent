from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from app.agent.exceptions import StorageError


class GraphStore:
    """封装 NetworkX DiGraph 的图存储，JSON 序列化。"""

    def __init__(self, namespace: str, storage_dir: str):
        self.namespace = namespace
        self.storage_dir = Path(storage_dir)
        self._graph = nx.DiGraph()

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    def initialize(self):
        """从磁盘加载图数据（JSON 格式）。"""
        path = self._path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._graph = nx.node_link_graph(data)
            except Exception as e:
                raise StorageError(f"Graph 加载失败 ({self.namespace}): {e}") from e

    def persist(self):
        """持久化到磁盘（JSON 格式）。"""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._graph)
        with open(self._path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def _path(self) -> Path:
        return self.storage_dir / f"{self.namespace}.graph.json"
