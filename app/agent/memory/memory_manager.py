from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import numpy as np

from app.agent.constants import (
    CORE_MEMORY_WEIGHT,
    MEMORY_TOP_K,
    WORKING_MEMORY_TTL,
    WORKING_MEMORY_WEIGHT,
)
from app.agent.storage.redis_kv_store import RedisKVStore


def _text_similarity(a: str, b: str) -> float:
    """基于字符三元组的 Jaccard 相似度，用于检测近似重复的记忆。"""
    if not a or not b:
        return 0.0
    a_grams = {a[i:i+3] for i in range(len(a) - 2)}
    b_grams = {b[i:i+3] for i in range(len(b) - 2)}
    if not a_grams or not b_grams:
        return 0.0
    intersection = a_grams & b_grams
    union = a_grams | b_grams
    return len(intersection) / len(union)


def _merge_meta(target: dict, source: dict) -> None:
    """将 source 的内容合并到 target，保留更高的重要性和最新的时间戳。"""
    # 合并文本
    target_text = target.get("text", "")
    source_text = source.get("text", "")
    if source_text not in target_text:
        target["text"] = f"{target_text}；{source_text}"

    # 保留更高的重要性
    target["importance"] = max(
        target.get("importance", 0), source.get("importance", 0)
    )

    # 保留最新的时间戳
    s_ts = source.get("timestamp", "")
    t_ts = target.get("timestamp", "")
    if s_ts > t_ts:
        target["timestamp"] = s_ts


class MemoryManager:
    """记忆管理器：统筹提取、存储、检索和剪枝。

    所有记忆存储在 Redis 中（通过 RedisKVStore），按重要性和类型分
    core_memories / working_memories 两个命名空间。
    检索时加载用户的所有记忆，在内存中计算余弦相似度、加权融合和时间衰减。
    使用 Redis 替代 FAISS 的原因：单个用户的记忆量通常 < 500 条，
    全量扫描 + 暴力搜索的性能足够，且避免了 FAISS 的删除重建开销和文件持久化脆弱性。
    """

    def __init__(self, tenant_id: str = "default"):
        prefix = tenant_id if tenant_id else "default"
        self.core_memory_kv = RedisKVStore(f"core_memories:{prefix}")
        self.working_memory_kv = RedisKVStore(f"working_memories:{prefix}")
        self.user_profiles_kv = RedisKVStore(f"user_profiles:{prefix}")
        self.conversations_kv = RedisKVStore(f"conversations:{prefix}")

    def initialize(self):
        self.core_memory_kv.initialize()
        self.working_memory_kv.initialize()
        self.user_profiles_kv.initialize()
        self.conversations_kv.initialize()

    def finalize(self):
        self.core_memory_kv.persist()
        self.working_memory_kv.persist()
        self.user_profiles_kv.persist()
        self.conversations_kv.persist()

    # ---- 用户画像 ----

    async def get_user_profile(self, user_id: str) -> dict:
        """获取用户画像，不存在时返回默认画像。"""
        profile = self.user_profiles_kv.get_by_id(user_id)
        if profile is None:
            return self._default_profile(user_id)
        return profile

    async def update_user_profile(
        self,
        user_id: str,
        message: str = "",
        answer: str = "",
        topics: list[str] | None = None,
    ):
        """更新用户画像：话题频次、偏好统计、最近交互时间。"""
        profile = await self.get_user_profile(user_id)
        profile.setdefault("user_id", user_id)

        if topics:
            topics_count: dict = profile.setdefault("topics", {})
            for t in topics:
                topics_count[t] = topics_count.get(t, 0) + 1

        profile["total_interactions"] = profile.get("total_interactions", 0) + 1
        history: list = profile.setdefault("recent_history", [])
        history.append({
            "message": message,
            "answer": answer[:200],
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        if len(history) > 20:
            history.pop(0)

        profile["last_active"] = datetime.now(timezone.utc).isoformat()
        self.user_profiles_kv.upsert({user_id: profile})

    # ---- 记忆存储 ----

    async def store_session_memory(
        self,
        user_id: str,
        session_id: str,
        memories: list[dict],
        embeddings_api,
        importance_threshold: float = 0.3,
    ):
        """存储从会话中提取的记忆到核心/工作记忆库。

        importance >= threshold 的记忆存入核心记忆，其余入工作记忆。
        """
        if not memories:
            return

        now = datetime.now(timezone.utc).isoformat()
        memory_batch_id = uuid4().hex

        core_entries: dict[str, dict] = {}
        working_entries: dict[str, dict] = {}

        for i, m in enumerate(memories):
            imp = m.get("importance", 0.5)
            mem_id = f"{user_id}_{session_id}_{memory_batch_id}_{i}"
            text = f"{m.get('type', '')}: {m.get('content', '')}"
            entry = {
                "text": text,
                "type": m.get("type", ""),
                "importance": imp,
                "embedding": self._l2_normalize(
                    embeddings_api.embed_documents([text])[0]
                ),
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": now,
            }

            if imp >= importance_threshold:
                core_entries[mem_id] = entry
            else:
                working_entries[mem_id] = entry

        if core_entries:
            self.core_memory_kv.upsert(core_entries)
        if working_entries:
            self.working_memory_kv.upsert(working_entries)

    # ---- 记忆检索 ----

    async def get_relevant_memories(
        self,
        user_id: str,
        query: str,
        embeddings_api,
        k: int = MEMORY_TOP_K,
    ) -> list[dict]:
        """检索用户的相关记忆：余弦相似度 + 加权融合 + 时间衰减。

        全量加载该用户的所有记忆，在内存中暴力搜索。
        对核心记忆应用权重 CORE_MEMORY_WEIGHT（0.6），
        对工作记忆应用 WORKING_MEMORY_WEIGHT（0.4）并按 24h TTL 线性衰减。
        """
        if not query:
            return []

        query_emb = self._l2_normalize(
            embeddings_api.embed_documents([query])[0]
        )
        now = datetime.now(timezone.utc)
        results: list[dict] = []

        for _, entry in self.core_memory_kv.get_all():
            if entry.get("user_id") != user_id:
                continue
            score = self._compute_score(entry, query_emb, is_core=True, now=now)
            if score > 0:
                results.append(self._format_result(entry, score))

        for _, entry in self.working_memory_kv.get_all():
            if entry.get("user_id") != user_id:
                continue
            score = self._compute_score(entry, query_emb, is_core=False, now=now)
            if score > 0:
                results.append(self._format_result(entry, score))

        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return results[:k]

    # ---- 会话历史 ----

    async def get_session_history(self, user_id: str, limit: int = 5) -> list[dict]:
        """获取用户近期会话历史。"""
        profile = await self.get_user_profile(user_id)
        history = profile.get("recent_history", [])
        return history[-limit:] if history else []

    # ---- 记忆剪枝 ----

    async def prune_expired_memories(self):
        """剪枝过期的工作记忆（超过 WORKING_MEMORY_TTL 的条目）。"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=WORKING_MEMORY_TTL)
        expired = [
            key for key, entry in self.working_memory_kv.get_all()
            if _ts_before(entry.get("timestamp", ""), cutoff)
        ]
        if expired:
            self.working_memory_kv.mdelete(expired)

    # ---- 记忆合并 ----

    async def consolidate_memories(self, similarity_threshold: float = 0.85):
        """合并相似的核心记忆，防止记忆库膨胀。

        按用户分组后计算两两之间的字符三元组 Jaccard 相似度，
        超过阈值的条目合并到第一条，然后删除其余重复的条目。
        """
        all_items = list(self.core_memory_kv.get_all())
        user_groups: dict[str, list[tuple[str, dict]]] = {}
        for key, entry in all_items:
            uid = entry.get("user_id", "")
            user_groups.setdefault(uid, []).append((key, entry))

        for items in user_groups.values():
            if len(items) < 2:
                continue

            merged_keys: set[str] = set()

            for i in range(len(items)):
                if items[i][0] in merged_keys:
                    continue
                for j in range(i + 1, len(items)):
                    if items[j][0] in merged_keys:
                        continue
                    sim = _text_similarity(
                        items[i][1].get("text", ""),
                        items[j][1].get("text", ""),
                    )
                    if sim >= similarity_threshold:
                        _merge_meta(items[i][1], items[j][1])
                        merged_keys.add(items[j][0])

            if merged_keys:
                # 写回所有被 _merge_meta 修改过的锚点（可能有多个独立锚点）
                for k, v in items:
                    if k not in merged_keys:
                        self.core_memory_kv.upsert({k: v})
                # 删除被合并的条目
                self.core_memory_kv.mdelete(list(merged_keys))

    # ---- 遗忘 ----

    async def forget_user(self, user_id: str):
        """删除用户的所有记忆和画像。"""
        self.user_profiles_kv.mdelete([user_id])

        for kv in [self.core_memory_kv, self.working_memory_kv]:
            ids = [k for k, v in kv.get_all() if v.get("user_id") == user_id]
            if ids:
                kv.mdelete(ids)

    # ---- 内部工具方法 ----

    @staticmethod
    def _default_profile(user_id: str) -> dict:
        return {
            "user_id": user_id, "topics": {},
            "recent_history": [], "total_interactions": 0,
        }

    @staticmethod
    def _l2_normalize(vec: list[float]) -> list[float]:
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.tolist()

    @staticmethod
    def _compute_score(
        entry: dict, query_emb: list[float],
        is_core: bool, now: datetime,
    ) -> float:
        emb = entry.get("embedding")
        if not emb:
            return 0.0

        score = float(np.dot(np.array(query_emb), np.array(emb)))
        if not is_core:
            score *= WORKING_MEMORY_WEIGHT
            ts_str = entry.get("timestamp", "")
            age = _parse_age_hours(ts_str, now)
            if age is not None:
                score *= max(0.0, 1.0 - age / WORKING_MEMORY_TTL)
        else:
            score *= CORE_MEMORY_WEIGHT
        return score

    @staticmethod
    def _format_result(entry: dict, score: float) -> dict:
        return {
            "text": entry.get("text", ""),
            "metadata": {
                "type": entry.get("type", ""),
                "importance": entry.get("importance", 0),
                "user_id": entry.get("user_id", ""),
                "timestamp": entry.get("timestamp", ""),
            },
            "score": score,
        }


def _ts_before(ts_str: str, cutoff: datetime) -> bool:
    if not ts_str:
        return False
    try:
        return datetime.fromisoformat(ts_str) < cutoff
    except (ValueError, TypeError):
        return False


def _parse_age_hours(ts_str: str, now: datetime) -> float | None:
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str)
        return (now - ts).total_seconds() / 3600
    except (ValueError, TypeError):
        return None
