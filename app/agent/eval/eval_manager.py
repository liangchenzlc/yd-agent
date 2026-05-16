from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.agent.constants import EVAL_MAX_RECENT_RUNS, EVAL_SCORE_BUCKETS
from app.agent.storage.redis_kv_store import RedisKVStore


class EvalManager:
    """评估管理器：统筹评估记录的存储、检索、统计和维护。

    使用 RedisKVStore 替代原有的文件存储，所有操作通过公共 API 完成，
    不依赖内部 _data 字典。
    """

    def __init__(self, tenant_id: str = "default"):
        prefix = tenant_id if tenant_id else "default"
        self.eval_runs_kv = RedisKVStore(f"eval_runs:{prefix}")
        self.hard_cases_kv = RedisKVStore(f"hard_cases:{prefix}")
        self.feedback_kv = RedisKVStore(f"feedback:{prefix}")
        self.eval_stats_kv = RedisKVStore(f"eval_stats:{prefix}")

    def initialize(self):
        self.eval_runs_kv.initialize()
        self.hard_cases_kv.initialize()
        self.feedback_kv.initialize()
        self.eval_stats_kv.initialize()
        if self.eval_stats_kv.get_by_id("global") is None:
            self._reset_stats()

    def finalize(self):
        pass

    # ---- Eval Run 操作 ----

    async def add_eval_run(self, eval_item: dict) -> str:
        run_id = eval_item.get("run_id", uuid.uuid4().hex[:12])
        eval_item["run_id"] = run_id
        key = f"{eval_item.get('user_id', 'unknown')}_{run_id}"
        self.eval_runs_kv.upsert({key: eval_item})
        return run_id

    async def get_eval_run(self, run_id: str) -> dict | None:
        for key in self.eval_runs_kv.keys():
            val = self.eval_runs_kv.get_by_id(key)
            if val and val.get("run_id") == run_id:
                return val
        return None

    async def list_eval_runs(
        self, limit: int = 50, offset: int = 0,
        min_score: int = 0, max_score: int = 10,
    ) -> list[dict]:
        runs = []
        for _, val in self.eval_runs_kv.get_all():
            if min_score <= val.get("overall_score", 0) <= max_score:
                runs.append(val)
        runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return runs[offset:offset + limit]

    async def count_eval_runs(self, min_score: int = 0, max_score: int = 10) -> int:
        count = 0
        for _, val in self.eval_runs_kv.get_all():
            if min_score <= val.get("overall_score", 0) <= max_score:
                count += 1
        return count

    async def delete_eval_runs(self) -> int:
        count = len(self.eval_runs_kv)
        self.eval_runs_kv.clear()
        self._reset_stats()
        return count

    async def get_recent_runs(self, n: int = 20) -> list[dict]:
        runs = [val for _, val in self.eval_runs_kv.get_all()]
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
        for _, val in self.hard_cases_kv.get_all():
            if val.get("case_id") == case_id:
                return val
        return None

    async def list_hard_cases(
        self, reviewed: bool | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        cases = [val for _, val in self.hard_cases_kv.get_all()]
        if reviewed is not None:
            cases = [c for c in cases if c.get("reviewed", False) == reviewed]
        cases.sort(key=lambda c: c.get("timestamp", ""), reverse=True)
        return cases[offset:offset + limit]

    async def mark_case_reviewed(self, case_id: str) -> bool:
        for key in self.hard_cases_kv.keys():
            val = self.hard_cases_kv.get_by_id(key)
            if val and val.get("case_id") == case_id:
                val["reviewed"] = True
                self.hard_cases_kv.upsert({key: val})
                return True
        return False

    async def count_hard_cases(self, reviewed: bool | None = None) -> int:
        cases = [val for _, val in self.hard_cases_kv.get_all()]
        if reviewed is not None:
            cases = [c for c in cases if c.get("reviewed", False) == reviewed]
        return len(cases)

    async def delete_hard_cases(self) -> int:
        count = len(self.hard_cases_kv)
        self.hard_cases_kv.clear()
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
        items = [val for _, val in self.feedback_kv.get_all()]
        if user_id:
            items = [f for f in items if f.get("user_id") == user_id]
        items.sort(key=lambda f: f.get("timestamp", ""), reverse=True)
        return items[offset:offset + limit]

    async def count_feedback(self, user_id: str | None = None) -> int:
        items = [val for _, val in self.feedback_kv.get_all()]
        if user_id:
            items = [f for f in items if f.get("user_id") == user_id]
        return len(items)

    async def get_feedback_stats(self) -> dict:
        items = [val for _, val in self.feedback_kv.get_all()]
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

        for bucket in EVAL_SCORE_BUCKETS:
            low, high = bucket.split("-")
            if int(low) <= score <= int(high):
                dist = stats.setdefault("score_distribution", {})
                dist[bucket] = dist.get(bucket, 0) + 1
                break

        passed = stats.get("total_passed", 0) + (1 if score >= 6 else 0)
        stats["total_passed"] = passed
        stats["pass_rate"] = round(passed / stats["total_eval_runs"], 2)

        self.eval_stats_kv.upsert({"global": stats})

    # ---- 维护 ----

    async def purge_expired_runs(self, retention_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        expired_keys = []
        for key, val in self.eval_runs_kv.get_all():
            ts_str = val.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff:
                        expired_keys.append(key)
                except (ValueError, TypeError):
                    pass
        if expired_keys:
            self.eval_runs_kv.mdelete(expired_keys)
        return len(expired_keys)

    async def cap_max_runs(self, max_runs: int = EVAL_MAX_RECENT_RUNS) -> int:
        if len(self.eval_runs_kv) <= max_runs:
            return 0
        items = self.eval_runs_kv.get_all()
        items.sort(key=lambda kv: kv[1].get("timestamp", ""))
        to_remove = [k for k, _ in items[:len(items) - max_runs]]
        if to_remove:
            self.eval_runs_kv.mdelete(to_remove)
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
