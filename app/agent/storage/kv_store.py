from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.exceptions import StorageError


class JsonKVStore:
    """JSON 文件 KV 存储，用于存储文档文本 chunk 等。"""

    def __init__(self, namespace: str, storage_dir: str):
        self.namespace = namespace
        self.storage_dir = Path(storage_dir)
        self._data: dict[str, Any] = {}

    def initialize(self):
        """从磁盘加载。"""
        path = self.storage_dir / f"{self.namespace}.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                raise StorageError(f"KV 存储加载失败 ({self.namespace}): {e}") from e

    def get_by_id(self, key: str) -> Any | None:
        return self._data.get(key)

    def mget(self, keys: list[str]) -> list[Any | None]:
        return [self._data.get(k) for k in keys]

    def mset(self, pairs: dict[str, Any]):
        """批量写入。"""
        self._data.update(pairs)

    def upsert(self, pairs: dict[str, Any]):
        """批量幂等写入（同 mset）。"""
        self._data.update(pairs)

    def mdelete(self, keys: list[str]):
        for k in keys:
            self._data.pop(k, None)

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def persist(self):
        """持久化到磁盘。"""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        with open(self.storage_dir / f"{self.namespace}.json", "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def __len__(self) -> int:
        return len(self._data)
