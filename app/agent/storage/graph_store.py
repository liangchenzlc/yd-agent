from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import networkx as nx

from app.agent.exceptions import StorageError


class GraphStore:
    """封装 NetworkX DiGraph 的图存储。"""

    def __init__(self, namespace: str, storage_dir: str):
        self.namespace = namespace
        self.storage_dir = Path(storage_dir)
        self._graph = nx.DiGraph()

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    def initialize(self):
        """从磁盘加载图数据。"""
        path = self.storage_dir / f"{self.namespace}.graph"
        if path.exists():
            try:
                with open(path, "rb") as f:
                    self._graph = pickle.load(f)
            except Exception as e:
                raise StorageError(f"Graph 加载失败 ({self.namespace}): {e}") from e

    def upsert_node(self, node_id: str, node_data: dict[str, Any]):
        """幂等写入节点。"""
        if node_id in self._graph:
            existing = self._graph.nodes[node_id]
            existing.update(node_data)
        else:
            self._graph.add_node(node_id, **(node_data or {}))

    def upsert_edge(
        self,
        source: str,
        target: str,
        edge_data: dict[str, Any] | None = None,
    ):
        """幂等写入边。"""
        if self._graph.has_edge(source, target):
            existing = self._graph.edges[source, target]
            if edge_data:
                existing.update(edge_data)
        else:
            self._graph.add_edge(source, target, **(edge_data or {}))

    def get_nodes_batch(self, node_ids: list[str]) -> list[tuple[str, dict]]:
        """批量获取节点。"""
        return [(n, dict(self._graph.nodes[n])) for n in node_ids if n in self._graph]

    def get_edges_batch(
        self, node_ids: list[str] | None = None
    ) -> list[tuple[str, str, dict]]:
        """批量获取边；node_ids 为 None 返回全部边。"""
        if node_ids is None:
            return list(self._graph.edges(data=True))
        edges = []
        for u, v, d in self._graph.edges(data=True):
            if u in node_ids or v in node_ids:
                edges.append((u, v, dict(d) if d else {}))
        return edges

    def get_all_nodes(self) -> list[tuple[str, dict]]:
        return list(self._graph.nodes(data=True))

    def get_all_edges(self) -> list[tuple[str, str, dict]]:
        return list(self._graph.edges(data=True))

    def delete_node(self, node_id: str):
        """删除节点及关联边。"""
        if node_id in self._graph:
            self._graph.remove_node(node_id)

    def persist(self):
        """持久化到磁盘。"""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        with open(self.storage_dir / f"{self.namespace}.graph", "wb") as f:
            pickle.dump(self._graph, f, protocol=pickle.HIGHEST_PROTOCOL)

    def __len__(self) -> int:
        return self._graph.number_of_nodes()
