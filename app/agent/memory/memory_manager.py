from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.agent.constants import (
    CORE_MEMORY_WEIGHT,
    DEFAULT_USER_ID,
    MEMORY_TOP_K,
    WORKING_MEMORY_TTL,
    WORKING_MEMORY_WEIGHT,
)
from app.agent.storage.kv_store import JsonKVStore
from app.agent.storage.vector_store import FAISSStore


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
    t_meta = target.setdefault("metadata", {})
    s_meta = source.get("metadata", {})

    # 合并文本
    target_text = target.get("text", "")
    source_text = source.get("text", "")
    if source_text not in target_text:
        target["text"] = f"{target_text}；{source_text}"

    # 保留更高的重要性
    t_imp = t_meta.get("importance", 0)
    s_imp = s_meta.get("importance", 0)
    t_meta["importance"] = max(t_imp, s_imp)

    # 保留最新的时间戳
    t_ts = t_meta.get("timestamp", "")
    s_ts = s_meta.get("timestamp", "")
    if s_ts > t_ts:
        t_meta["timestamp"] = s_ts


class MemoryManager:
    """记忆管理器：统筹提取、存储、检索和剪枝。"""

    def __init__(self, storage_dir: str, embedding_dim: int = 1024):
        self.core_memory_vdb = FAISSStore("core_memory", storage_dir, embedding_dim)
        self.working_memory_vdb = FAISSStore("working_memory", storage_dir, embedding_dim)
        self.user_profiles_kv = JsonKVStore("user_profiles", storage_dir)
        self.conversations_kv = JsonKVStore("conversations", storage_dir)

    def initialize(self):
        self.core_memory_vdb.initialize()
        self.working_memory_vdb.initialize()
        self.user_profiles_kv.initialize()
        self.conversations_kv.initialize()

    def finalize(self):
        self.core_memory_vdb.persist()
        self.working_memory_vdb.persist()
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

        # 更新话题频次
        if topics:
            topics_count: dict = profile.setdefault("topics", {})
            for t in topics:
                topics_count[t] = topics_count.get(t, 0) + 1

        # 更新交互统计
        profile["total_interactions"] = profile.get("total_interactions", 0) + 1
        # 保留最近 20 条消息历史用于上下文
        history: list = profile.setdefault("recent_history", [])
        history.append({"message": message, "answer": answer[:200], "ts": datetime.now(timezone.utc).isoformat()})
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

        core_ids = []
        core_texts = []
        core_embs = []
        core_metas = []

        working_ids = []
        working_texts = []
        working_embs = []
        working_metas = []

        now = datetime.now(timezone.utc).isoformat()
        memory_batch_id = uuid4().hex

        for i, m in enumerate(memories):
            imp = m.get("importance", 0.5)
            mem_id = f"{user_id}_{session_id}_{memory_batch_id}_{i}"
            text = f"{m.get('type', '')}: {m.get('content', '')}"
            meta = {
                "type": m.get("type", ""),
                "importance": imp,
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": now,
            }

            if imp >= importance_threshold:
                core_ids.append(mem_id)
                texts_to_embed: list[str] = [text]
                embs = embeddings_api.embed_documents(texts_to_embed)
                core_texts.append(text)
                core_embs.append(embs[0])
                core_metas.append(meta)
            else:
                working_ids.append(mem_id)
                texts_to_embed = [text]
                embs = embeddings_api.embed_documents(texts_to_embed)
                working_texts.append(text)
                working_embs.append(embs[0])
                working_metas.append(meta)

        if core_ids:
            self.core_memory_vdb.add_texts(core_ids, core_texts, core_embs, core_metas)
        if working_ids:
            self.working_memory_vdb.add_texts(working_ids, working_texts, working_embs, working_metas)

    # ---- 记忆检索 ----

    async def get_relevant_memories(
        self,
        user_id: str,
        query: str,
        embeddings_api,
        k: int = MEMORY_TOP_K,
    ) -> list[dict]:
        """检索用户的相关记忆：时间加权融合核心记忆 + 工作记忆。"""
        if not query:
            return []

        emb = embeddings_api.embed_documents([query])[0]

        core_results = self.core_memory_vdb.similarity_search_by_vector(emb, k=k)
        working_results = self.working_memory_vdb.similarity_search_by_vector(emb, k=k)

        # 过滤当前用户
        core_results = [r for r in core_results if r.get("metadata", {}).get("user_id") == user_id]
        working_results = [r for r in working_results if r.get("metadata", {}).get("user_id") == user_id]

        # 时间衰减：工作记忆按年龄衰减
        now = datetime.now(timezone.utc)
        for r in working_results:
            ts_str = r.get("metadata", {}).get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    age_hours = (now - ts).total_seconds() / 3600
                    decay = max(0.0, 1.0 - age_hours / WORKING_MEMORY_TTL)
                    r["score"] = r.get("score", 0) * decay
                    r["decay"] = decay
                except (ValueError, TypeError):
                    pass

        # 归一化分数
        for r in core_results:
            r["score"] = r.get("score", 0) * CORE_MEMORY_WEIGHT
        for r in working_results:
            r["score"] = r.get("score", 0) * WORKING_MEMORY_WEIGHT

        all_results = core_results + working_results
        all_results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return all_results[:k]

    # ---- 会话历史 ----

    async def get_session_history(self, user_id: str, limit: int = 5) -> list[dict]:
        """获取用户近期会话历史。"""
        profile = await self.get_user_profile(user_id)
        history = profile.get("recent_history", [])
        return history[-limit:] if history else []

    # ---- 记忆剪枝 ----

    async def prune_expired_memories(self):
        """剪枝过期的工作记忆。"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=WORKING_MEMORY_TTL)

        expired_ids = []
        # 检查工作记忆的元数据
        for mem_id, meta in list(self.working_memory_vdb.get_all_meta_items()):
            ts_str = meta.get("metadata", {}).get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff:
                        expired_ids.append(mem_id)
                except (ValueError, TypeError):
                    pass

        if expired_ids:
            self.working_memory_vdb.delete(expired_ids)

    # ---- 记忆合并 ----

    async def consolidate_memories(self, similarity_threshold: float = 0.85):
        """合并相似的核心记忆，防止记忆库膨胀。"""
        # 按用户分组
        user_groups: dict[str, list[tuple[str, dict]]] = {}
        for mem_id, meta in list(self.core_memory_vdb.get_all_meta_items()):
            uid = meta.get("metadata", {}).get("user_id", "")
            user_groups.setdefault(uid, []).append((mem_id, meta))

        for uid, items in user_groups.items():
            if len(items) < 2:
                continue
            merged_ids: set[str] = set()
            for i in range(len(items)):
                if items[i][0] in merged_ids:
                    continue
                for j in range(i + 1, len(items)):
                    if items[j][0] in merged_ids:
                        continue
                    sim = _text_similarity(
                        items[i][1].get("text", ""),
                        items[j][1].get("text", ""),
                    )
                    if sim >= similarity_threshold:
                        _merge_meta(items[i][1], items[j][1])
                        merged_ids.add(items[j][0])

            if merged_ids:
                self.core_memory_vdb.delete(list(merged_ids))
                self.core_memory_vdb.persist()

    # ---- 遗忘 ----

    async def forget_user(self, user_id: str):
        """删除用户的所有记忆和画像。"""
        # KV 删除
        self.user_profiles_kv.mdelete([user_id])
        # FAISS 删除——收集该用户的记忆 ID
        core_ids = [k for k, v in self.core_memory_vdb.get_all_meta_items() if v.get("metadata", {}).get("user_id") == user_id]
        working_ids = [k for k, v in self.working_memory_vdb.get_all_meta_items() if v.get("metadata", {}).get("user_id") == user_id]
        self.core_memory_vdb.delete(core_ids)
        self.working_memory_vdb.delete(working_ids)

    @staticmethod
    def _default_profile(user_id: str) -> dict:
        return {"user_id": user_id, "topics": {}, "recent_history": [], "total_interactions": 0}
