from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.agent.constants import EVAL_MAX_RECENT_RUNS, EVAL_SCORE_BUCKETS
from app.agent.storage.kv_store import JsonKVStore


class EvalManager:
    """评估管理器：统筹评估记录的存储、检索、统计和维护。"""

    def __init__(self, storage_dir: str):
        self.eval_runs_kv = JsonKVStore("eval_runs", storage_dir)
        self.hard_cases_kv = JsonKVStore("hard_cases", storage_dir)
        self.feedback_kv = JsonKVStore("feedback", storage_dir)
        self.eval_stats_kv = JsonKVStore("eval_stats", storage_dir)

    def initialize(self):
        self.eval_runs_kv.initialize()
        self.hard_cases_kv.initialize()
        self.feedback_kv.initialize()
        self.eval_stats_kv.initialize()
        # 确保 stats 有默认值
        if self.eval_stats_kv.get_by_id("global") is None:
            self._reset_stats()

    def finalize(self):
        self.eval_runs_kv.persist()
        self.hard_cases_kv.persist()
        self.feedback_kv.persist()
        self.eval_stats_kv.persist()

    # ---- Eval Run 操作 ----

    async def add_eval_run(self, eval_item: dict) -> str:
        run_id = eval_item.get("run_id", uuid.uuid4().hex[:12])
        eval_item["run_id"] = run_id
        key = f"{eval_item.get('user_id', 'unknown')}_{run_id}"
        self.eval_runs_kv.upsert({key: eval_item})
        return run_id

    async def get_eval_run(self, run_id: str) -> dict | None:
        for key, val in self.eval_runs_kv._data.items():
            if val.get("run_id") == run_id:
                return val
        return None

    async def list_eval_runs(
        self, limit: int = 50, offset: int = 0,
        min_score: int = 0, max_score: int = 10,
    ) -> list[dict]:
        runs = [
            v for v in self.eval_runs_kv._data.values()
            if min_score <= v.get("overall_score", 0) <= max_score
        ]
        runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return runs[offset:offset + limit]

    async def count_eval_runs(self, min_score: int = 0, max_score: int = 10) -> int:
        return sum(
            1 for v in self.eval_runs_kv._data.values()
            if min_score <= v.get("overall_score", 0) <= max_score
        )

    async def delete_eval_runs(self) -> int:
        count = len(self.eval_runs_kv._data)
        self.eval_runs_kv._data.clear()
        self._reset_stats()
        return count

    async def get_recent_runs(self, n: int = 20) -> list[dict]:
        runs = list(self.eval_runs_kv._data.values())
        runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return runs[:n]

    # ---- Hard Case 操作 ----

    async def add_hard_case(self, case: dict) -> str:
        case_id = case.get("case_id", uuid.uuid4().hex[:12])
        case["case_id"] = case_id
        key = f"{case.get('user_id', 'unknown')}_{case_id}"
        self.hard_cases_kv.upsert({key: case})
        return case_id

    async def get_hard_case(self, case_id: str) -> dict | None:
        for key, val in self.hard_cases_kv._data.items():
            if val.get("case_id") == case_id:
                return val
        return None

    async def list_hard_cases(
        self, reviewed: bool | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        cases = list(self.hard_cases_kv._data.values())
        if reviewed is not None:
            cases = [c for c in cases if c.get("reviewed", False) == reviewed]
        cases.sort(key=lambda c: c.get("timestamp", ""), reverse=True)
        return cases[offset:offset + limit]

    async def mark_case_reviewed(self, case_id: str) -> bool:
        for key, val in self.hard_cases_kv._data.items():
            if val.get("case_id") == case_id:
                val["reviewed"] = True
                return True
        return False

    async def count_hard_cases(self, reviewed: bool | None = None) -> int:
        cases = self.hard_cases_kv._data.values()
        if reviewed is not None:
            cases = [c for c in cases if c.get("reviewed", False) == reviewed]
        return len(list(cases))

    async def delete_hard_cases(self) -> int:
        count = len(self.hard_cases_kv._data)
        self.hard_cases_kv._data.clear()
        return count

    # ---- Feedback 操作 ----

    async def add_feedback(self, feedback: dict) -> str:
        fid = feedback.get("feedback_id", uuid.uuid4().hex[:12])
        feedback["feedback_id"] = fid
        key = f"{feedback.get('user_id', 'unknown')}_{fid}"
        self.feedback_kv.upsert({key: feedback})
        return fid

    async def list_feedback(
        self, user_id: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        items = list(self.feedback_kv._data.values())
        if user_id:
            items = [f for f in items if f.get("user_id") == user_id]
        items.sort(key=lambda f: f.get("timestamp", ""), reverse=True)
        return items[offset:offset + limit]

    async def count_feedback(self, user_id: str | None = None) -> int:
        items = self.feedback_kv._data.values()
        if user_id:
            items = [f for f in items if f.get("user_id") == user_id]
        return len(list(items))

    async def get_feedback_stats(self) -> dict:
        items = list(self.feedback_kv._data.values())
        up = sum(1 for f in items if f.get("thumbs_up"))
        down = len(items) - up
        return {
            "thumbs_up": up,
            "thumbs_down": down,
            "total": len(items),
            "ratio": up / len(items) if items else 0.0,
        }

    # ---- Stats 操作 ----

    async def get_eval_summary(self) -> dict:
        stats = self.eval_stats_kv.get_by_id("global") or self._default_stats()
        recent = await self.get_recent_runs(20)
        recent_scores = [r.get("overall_score", 0) for r in recent]
        stats["recent_avg_score"] = round(sum(recent_scores) / len(recent_scores), 2) if recent_scores else 0.0
        stats["total_hard_cases"] = await self.count_hard_cases()
        stats["total_feedback"] = await self.count_feedback()
        return stats

    async def update_stats(self, score: int) -> None:
        stats = self.eval_stats_kv.get_by_id("global") or self._default_stats()
        stats["total_eval_runs"] = stats.get("total_eval_runs", 0) + 1
        stats["total_score"] = stats.get("total_score", 0) + score
        stats["avg_score"] = round(stats["total_score"] / stats["total_eval_runs"], 2)

        # 分桶
        for bucket in EVAL_SCORE_BUCKETS:
            low, high = bucket.split("-")
            if int(low) <= score <= int(high):
                dist = stats.setdefault("score_distribution", {})
                dist[bucket] = dist.get(bucket, 0) + 1
                break

        # 通过率 (score >= 6 为通过)
        passed = stats.get("total_passed", 0) + (1 if score >= 6 else 0)
        stats["total_passed"] = passed
        stats["pass_rate"] = round(passed / stats["total_eval_runs"], 2)

        self.eval_stats_kv.upsert({"global": stats})

    # ---- 维护 ----

    async def purge_expired_runs(self, retention_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        expired_keys = []
        for key, val in self.eval_runs_kv._data.items():
            ts_str = val.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff:
                        expired_keys.append(key)
                except (ValueError, TypeError):
                    pass
        for key in expired_keys:
            del self.eval_runs_kv._data[key]
        if expired_keys:
            self.eval_runs_kv.persist()
        return len(expired_keys)

    async def cap_max_runs(self, max_runs: int = EVAL_MAX_RECENT_RUNS) -> int:
        if len(self.eval_runs_kv._data) <= max_runs:
            return 0
        runs = list(self.eval_runs_kv._data.items())
        runs.sort(key=lambda kv: kv[1].get("timestamp", ""))
        to_remove = runs[:len(runs) - max_runs]
        for key, _ in to_remove:
            del self.eval_runs_kv._data[key]
        if to_remove:
            self.eval_runs_kv.persist()
        return len(to_remove)

    @staticmethod
    def _default_stats() -> dict:
        return {
            "total_eval_runs": 0,
            "total_score": 0,
            "avg_score": 0.0,
            "total_passed": 0,
            "pass_rate": 0.0,
            "score_distribution": {b: 0 for b in EVAL_SCORE_BUCKETS},
        }

    def _reset_stats(self):
        self.eval_stats_kv.upsert({"global": self._default_stats()})
