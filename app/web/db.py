from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config.settings import get_settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WebDatabase:
    """SQLite persistence layer for Web MVP."""

    def __init__(self, db_path: str | Path | None = None):
        settings = get_settings()
        self.db_path = Path(db_path or Path(settings.storage_dir) / "web.db")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists users (
                    id integer primary key autoincrement,
                    username text not null unique,
                    password_hash text not null,
                    role text not null default 'user',
                    enabled integer not null default 1,
                    tenant_id text,
                    created_at text not null
                );

                create table if not exists chat_sessions (
                    id text primary key,
                    user_id integer not null,
                    title text not null,
                    created_at text not null,
                    updated_at text not null,
                    tenant_id text not null default 'default',
                    foreign key(user_id) references users(id)
                );

                create table if not exists messages (
                    id integer primary key autoincrement,
                    session_id text not null,
                    user_id integer not null,
                    role text not null,
                    content text not null,
                    created_at text not null,
                    tenant_id text not null default 'default',
                    qa_log_id integer,
                    foreign key(session_id) references chat_sessions(id),
                    foreign key(user_id) references users(id)
                );

                create table if not exists qa_logs (
                    id integer primary key autoincrement,
                    session_id text not null,
                    user_id integer not null,
                    question text not null,
                    answer text not null,
                    workers text not null,
                    dispatch_reasoning text not null,
                    worker_results text not null,
                    confidence real,
                    created_at text not null,
                    tenant_id text not null default 'default'
                );

                create table if not exists documents (
                    id text primary key,
                    source text not null,
                    uploaded_by integer,
                    status text not null,
                    chunks integer not null default 0,
                    created_at text not null,
                    updated_at text not null,
                    tenant_id text not null default 'default'
                );

                create table if not exists feedback (
                    id integer primary key autoincrement,
                    qa_log_id integer not null,
                    user_id integer not null,
                    rating integer not null,
                    comment text not null default '',
                    created_at text not null,
                    tenant_id text not null default 'default',
                    foreign key(qa_log_id) references qa_logs(id),
                    foreign key(user_id) references users(id)
                );

                create table if not exists usage_stats (
                    date text not null,
                    category text not null,
                    key text not null,
                    value integer not null default 0,
                    primary key (date, category, key)
                );

                create table if not exists tenants (
                    id text primary key,
                    name text not null,
                    config text not null default '{}',
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists data_sources (
                    id integer primary key autoincrement,
                    tenant_id text not null unique,
                    db_type text not null default 'mysql',
                    db_host text not null default 'localhost',
                    db_port integer,
                    db_user text,
                    db_password text,
                    db_database text not null,
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists artifacts (
                    id text primary key,
                    tenant_id text not null,
                    user_id integer not null,
                    session_id text not null,
                    message_id integer,
                    qa_log_id integer,
                    worker text not null,
                    kind text not null,
                    filename text not null,
                    mime_type text not null,
                    size_bytes integer not null default 0,
                    storage_path text not null,
                    created_at text not null,
                    metadata text not null default '{}',
                    foreign key(session_id) references chat_sessions(id),
                    foreign key(user_id) references users(id)
                );
                """
            )
            self._ensure_column(conn, "chat_sessions", "tenant_id", "text not null default 'default'")
            self._ensure_column(conn, "messages", "tenant_id", "text not null default 'default'")
            self._ensure_column(conn, "messages", "qa_log_id", "integer")
            self._ensure_column(conn, "qa_logs", "tenant_id", "text not null default 'default'")
            self._ensure_column(conn, "documents", "tenant_id", "text not null default 'default'")
            self._ensure_column(conn, "feedback", "tenant_id", "text not null default 'default'")

    # ---- User CRUD ----

    def create_user(self, username: str, password_hash: str, role: str = "user",
                    tenant_id: str | None = None) -> dict[str, Any]:
        ALLOWED_ROLES = {"super_admin", "admin", "user"}
        if role not in ALLOWED_ROLES:
            raise ValueError(f"非法角色: {role}，允许: {', '.join(sorted(ALLOWED_ROLES))}")
        with self.connect() as conn:
            cur = conn.execute(
                "insert into users(username, password_hash, role, enabled, tenant_id, created_at) "
                "values (?, ?, ?, 1, ?, ?)",
                (username, password_hash, role, tenant_id, utc_now()),
            )
            return self.get_user_by_id(cur.lastrowid, conn=conn)

    def list_users(self, role: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """按角色和租户过滤用户。role/tenant_id 为 None 表示不限制。"""
        conditions = []
        params: list[Any] = []
        if role is not None:
            conditions.append("role = ?")
            params.append(role)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        where = " where " + " and ".join(conditions) if conditions else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"select id, username, role, enabled, tenant_id, created_at from users{where} order by id asc",
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def update_user(self, user_id: int, enabled: bool | None = None,
                    password_hash: str | None = None) -> dict[str, Any] | None:
        updates = []
        params: list[Any] = []
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        if password_hash is not None:
            updates.append("password_hash = ?")
            params.append(password_hash)
        if not updates:
            return self.get_user_by_id(user_id)
        params.append(user_id)
        with self.connect() as conn:
            conn.execute(f"update users set {', '.join(updates)} where id = ?", params)
            return self.get_user_by_id(user_id, conn=conn)

    def delete_user(self, user_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("delete from users where id = ?", (user_id,))
            return cur.rowcount > 0

    def count_users(self) -> int:
        with self.connect() as conn:
            row = conn.execute("select count(*) as total from users").fetchone()
            return int(row["total"])

    def count_by_role(self, role: str) -> int:
        with self.connect() as conn:
            row = conn.execute("select count(*) as total from users where role = ?", (role,)).fetchone()
            return int(row["total"])

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from users where username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
        if conn is not None:
            row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
            return dict(row) if row else None
        with self.connect() as local_conn:
            row = local_conn.execute("select * from users where id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"pragma table_info({table})").fetchall()
        if column not in {row["name"] for row in rows}:
            conn.execute(f"alter table {table} add column {column} {definition}")

    # ---- Session / Message / QA Log ----

    def create_session(self, user_id: int, session_id: str, title: str, tenant_id: str = "default") -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "insert into chat_sessions(id, user_id, title, created_at, updated_at, tenant_id) "
                "values (?, ?, ?, ?, ?, ?)",
                (session_id, user_id, title, now, now, tenant_id),
            )
        return {"id": session_id, "user_id": user_id, "title": title, "created_at": now, "updated_at": now}

    def ensure_session(self, user_id: int, session_id: str, title: str, tenant_id: str = "default") -> dict[str, Any]:
        session = self.get_session(user_id, session_id)
        if session:
            return session
        return self.create_session(user_id, session_id, title, tenant_id=tenant_id)

    def get_session(self, user_id: int, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from chat_sessions where id = ? and user_id = ?",
                (session_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    def list_sessions(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from chat_sessions where user_id = ? order by updated_at desc",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_session(self, user_id: int, session_id: str) -> bool:
        with self.connect() as conn:
            conn.execute("delete from artifacts where session_id = ? and user_id = ?", (session_id, user_id))
            conn.execute("delete from qa_logs where session_id = ? and user_id = ?", (session_id, user_id))
            conn.execute("delete from messages where session_id = ? and user_id = ?", (session_id, user_id))
            cur = conn.execute("delete from chat_sessions where id = ? and user_id = ?", (session_id, user_id))
            return cur.rowcount > 0

    def add_message(self, session_id: str, user_id: int, role: str, content: str,
                    tenant_id: str = "default", qa_log_id: int | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                "insert into messages(session_id, user_id, role, content, created_at, tenant_id, qa_log_id) "
                "values (?, ?, ?, ?, ?, ?, ?)",
                (session_id, user_id, role, content, now, tenant_id, qa_log_id),
            )
            conn.execute(
                "update chat_sessions set updated_at = ? where id = ? and user_id = ?",
                (now, session_id, user_id),
            )
            return {"id": cur.lastrowid, "session_id": session_id, "role": role,
                    "content": content, "created_at": now, "qa_log_id": qa_log_id}

    def update_message_qa_log(self, message_id: int, qa_log_id: int) -> None:
        with self.connect() as conn:
            conn.execute("update messages set qa_log_id = ? where id = ?", (qa_log_id, message_id))

    def list_messages(self, session_id: str, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select id, session_id, user_id, role, content, created_at, qa_log_id
                from messages
                where session_id = ? and user_id = ?
                order by id desc
                limit ?
                """,
                (session_id, user_id, limit),
            ).fetchall()
            messages = [dict(row) for row in reversed(rows)]

        # 附加产物信息
        artifact_map = self.list_artifacts_by_session(session_id, user_id)
        for msg in messages:
            raw_arts = artifact_map.get(msg["id"], [])
            msg["artifacts"] = [self.format_artifact(a) for a in raw_arts]

        return messages

    def add_qa_log(
        self,
        session_id: str,
        user_id: int,
        question: str,
        answer: str,
        workers: list[str],
        dispatch_reasoning: str,
        worker_results: list[dict[str, Any]],
        confidence: float | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into qa_logs(
                    session_id, user_id, question, answer, workers, dispatch_reasoning,
                    worker_results, confidence, created_at, tenant_id
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    question,
                    answer,
                    json.dumps(workers, ensure_ascii=False),
                    dispatch_reasoning,
                    json.dumps(worker_results, ensure_ascii=False),
                    confidence,
                    utc_now(),
                    tenant_id,
                ),
            )
            return {"id": cur.lastrowid}

    def list_qa_logs(self, limit: int = 100, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if tenant_id:
                rows = conn.execute(
                    "select * from qa_logs where tenant_id = ? order by id desc limit ?",
                    (tenant_id, limit),
                ).fetchall()
            else:
                rows = conn.execute("select * from qa_logs order by id desc limit ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    # ---- Document records ----

    def upsert_document(self, doc: dict[str, Any], tenant_id: str = "default") -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                insert into documents(id, source, uploaded_by, status, chunks, created_at, updated_at, tenant_id)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    source = excluded.source,
                    uploaded_by = excluded.uploaded_by,
                    status = excluded.status,
                    chunks = excluded.chunks,
                    updated_at = excluded.updated_at
                """,
                (
                    doc["id"],
                    doc.get("source", ""),
                    doc.get("uploaded_by"),
                    doc.get("status", "ready"),
                    doc.get("chunks", 0),
                    doc.get("created_at", now),
                    now,
                    tenant_id,
                ),
            )

    def delete_document_record(self, doc_id: str) -> None:
        with self.connect() as conn:
            conn.execute("delete from documents where id = ?", (doc_id,))

    def list_document_records(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if tenant_id:
                rows = conn.execute(
                    "select * from documents where tenant_id = ? order by updated_at desc",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute("select * from documents order by updated_at desc").fetchall()
            return [dict(row) for row in rows]

    # ---- Feedback ----

    def add_feedback(self, qa_log_id: int, user_id: int, rating: int, comment: str = "",
                     tenant_id: str = "default") -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                "insert into feedback(qa_log_id, user_id, rating, comment, created_at, tenant_id) "
                "values (?, ?, ?, ?, ?, ?)",
                (qa_log_id, user_id, rating, comment, utc_now(), tenant_id),
            )
            return {"id": cur.lastrowid}

    # ---- Hard Cases & Knowledge Gaps ----

    def list_hard_cases(self, limit: int = 100, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if tenant_id:
                rows = conn.execute(
                    """
                    select q.*, f.rating, f.comment
                    from qa_logs q
                    left join feedback f on f.qa_log_id = q.id
                    where (q.answer like '%未找到%' or q.confidence < 0.35 or f.rating < 0)
                    and q.tenant_id = ?
                    order by q.id desc
                    limit ?
                    """,
                    (tenant_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    select q.*, f.rating, f.comment
                    from qa_logs q
                    left join feedback f on f.qa_log_id = q.id
                    where q.answer like '%未找到%' or q.confidence < 0.35 or f.rating < 0
                    order by q.id desc
                    limit ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]

    def upsert_usage_stat(self, date: str, category: str, key: str, amount: int = 1) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into usage_stats(date, category, key, value) values (?, ?, ?, ?)
                on conflict(date, category, key) do update set value = value + excluded.value
                """,
                (date, category, key, amount),
            )

    def get_usage_stat(self, date: str, category: str, key: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "select value from usage_stats where date = ? and category = ? and key = ?",
                (date, category, key),
            ).fetchone()
            return int(row["value"]) if row else 0

    def list_knowledge_gaps(self, limit: int = 20, tenant_id: str | None = None) -> list[dict[str, Any]]:
        cases = self.list_hard_cases(limit=500, tenant_id=tenant_id)
        grouped: dict[str, dict[str, Any]] = {}
        for case in cases:
            question = str(case.get("question", "")).strip()
            if not question:
                continue
            key = self._normalize_gap_question(question)
            item = grouped.setdefault(
                key,
                {
                    "question": question,
                    "count": 0,
                    "reasons": {"not_found": 0, "low_confidence": 0, "negative_feedback": 0},
                    "latest_at": case.get("created_at", ""),
                    "examples": [],
                },
            )
            item["count"] += 1
            if "未找到" in str(case.get("answer", "")):
                item["reasons"]["not_found"] += 1
            confidence = case.get("confidence")
            if confidence is not None and confidence < 0.35:
                item["reasons"]["low_confidence"] += 1
            if (case.get("rating") or 0) < 0:
                item["reasons"]["negative_feedback"] += 1
            if case.get("created_at", "") > item["latest_at"]:
                item["latest_at"] = case.get("created_at", "")
            if len(item["examples"]) < 3:
                item["examples"].append({
                    "id": case.get("id"),
                    "question": question,
                    "answer": case.get("answer", ""),
                    "comment": case.get("comment", ""),
                })

        gaps = list(grouped.values())
        gaps.sort(key=lambda item: (item["count"], item["latest_at"]), reverse=True)
        for item in gaps:
            item["suggestion"] = self._gap_suggestion(item)
        return gaps[:limit]

    @staticmethod
    def _normalize_gap_question(question: str) -> str:
        return " ".join(question.lower().replace("？", "?").split())

    @staticmethod
    def _gap_suggestion(item: dict[str, Any]) -> str:
        reasons = item.get("reasons", {})
        if reasons.get("not_found", 0) >= reasons.get("negative_feedback", 0):
            return "建议补充或更新对应知识文档，确保知识库中包含该问题的明确答案。"
        if reasons.get("low_confidence", 0):
            return "建议补充更直接的 FAQ 条目，并优化相关文档标题和关键词。"
        return "建议人工复查已有答案，补充标准回答或纠正文档内容。"

    # ---- Tenant CRUD ----

    def list_tenants(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("select * from tenants order by created_at asc").fetchall()
            result = []
            for row in rows:
                tenant = dict(row)
                tenant["config"] = json.loads(tenant.get("config", "{}"))
                result.append(tenant)
            return result

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from tenants where id = ?", (tenant_id,)).fetchone()
            if row is None:
                return None
            tenant = dict(row)
            tenant["config"] = json.loads(tenant.get("config", "{}"))
            return tenant

    def create_tenant(self, tenant_id: str, name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        config_json = json.dumps(config or {}, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                "insert into tenants(id, name, config, created_at, updated_at) values (?, ?, ?, ?, ?)",
                (tenant_id, name, config_json, now, now),
            )
            return {"id": tenant_id, "name": name, "config": config or {}, "created_at": now, "updated_at": now}

    def update_tenant(self, tenant_id: str, name: str | None = None,
                      config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        updates = []
        params: list[Any] = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if config is not None:
            updates.append("config = ?")
            params.append(json.dumps(config, ensure_ascii=False))
        if not updates:
            return self.get_tenant(tenant_id)
        updates.append("updated_at = ?")
        params.append(utc_now())
        params.append(tenant_id)
        with self.connect() as conn:
            conn.execute(f"update tenants set {', '.join(updates)} where id = ?", params)
            return self.get_tenant(tenant_id)

    def delete_tenant(self, tenant_id: str) -> bool:
        with self.connect() as conn:
            conn.execute("delete from feedback where tenant_id = ?", (tenant_id,))
            conn.execute("delete from qa_logs where tenant_id = ?", (tenant_id,))
            conn.execute("delete from documents where tenant_id = ?", (tenant_id,))
            conn.execute(
                "delete from messages where user_id in (select id from users where tenant_id = ?)",
                (tenant_id,),
            )
            conn.execute(
                "delete from chat_sessions where user_id in (select id from users where tenant_id = ?)",
                (tenant_id,),
            )
            conn.execute("delete from users where tenant_id = ?", (tenant_id,))
            cur = conn.execute("delete from tenants where id = ?", (tenant_id,))
            return cur.rowcount > 0

    # ---- DataSource CRUD ----

    def upsert_data_source(self, tenant_id: str, db_type: str, db_host: str,
                           db_port: int | None, db_user: str, db_password: str,
                           db_database: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """insert into data_sources(tenant_id, db_type, db_host, db_port, db_user, db_password, db_database, created_at, updated_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   on conflict(tenant_id) do update set
                       db_type=excluded.db_type, db_host=excluded.db_host, db_port=excluded.db_port,
                       db_user=excluded.db_user, db_password=excluded.db_password,
                       db_database=excluded.db_database, updated_at=excluded.updated_at""",
                (tenant_id, db_type, db_host, db_port, db_user, db_password, db_database, now, now),
            )
            row = conn.execute(
                "select * from data_sources where tenant_id = ?", (tenant_id,)
            ).fetchone()
            return dict(row)

    def get_data_source(self, tenant_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from data_sources where tenant_id = ?", (tenant_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_data_source(self, tenant_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("delete from data_sources where tenant_id = ?", (tenant_id,))
            return cur.rowcount > 0

    # ---- Artifact CRUD ----

    def add_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        metadata_json = json.dumps(artifact.get("metadata", {}), ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """insert into artifacts(id, tenant_id, user_id, session_id, message_id, qa_log_id,
                   worker, kind, filename, mime_type, size_bytes, storage_path, created_at, metadata)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    artifact["id"],
                    artifact["tenant_id"],
                    artifact["user_id"],
                    artifact["session_id"],
                    artifact.get("message_id"),
                    artifact.get("qa_log_id"),
                    artifact["worker"],
                    artifact["kind"],
                    artifact["filename"],
                    artifact["mime_type"],
                    artifact.get("size_bytes", 0),
                    artifact["storage_path"],
                    artifact.get("created_at", utc_now()),
                    metadata_json,
                ),
            )
        return artifact

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from artifacts where id = ?", (artifact_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["metadata"] = json.loads(result.get("metadata", "{}"))
            return result

    def list_artifacts_by_message(self, message_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from artifacts where message_id = ? order by created_at asc",
                (message_id,),
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["metadata"] = json.loads(d.get("metadata", "{}"))
                result.append(d)
            return result

    def list_artifacts_by_qa_log(self, qa_log_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from artifacts where qa_log_id = ? order by created_at asc",
                (qa_log_id,),
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["metadata"] = json.loads(d.get("metadata", "{}"))
                result.append(d)
            return result

    def list_artifacts_by_session(self, session_id: str, user_id: int) -> dict[int, list[dict[str, Any]]]:
        """返回 session 内所有 message_id → artifacts 的映射。"""
        with self.connect() as conn:
            rows = conn.execute(
                "select * from artifacts where session_id = ? and user_id = ? order by created_at asc",
                (session_id, user_id),
            ).fetchall()
            mapping: dict[int, list[dict[str, Any]]] = {}
            for row in rows:
                d = dict(row)
                d["metadata"] = json.loads(d.get("metadata", "{}"))
                mid = d.get("message_id")
                if mid is not None:
                    mapping.setdefault(mid, []).append(d)
            return mapping

    def update_artifact_message(self, artifact_id: str, message_id: int, qa_log_id: int | None = None) -> None:
        with self.connect() as conn:
            if qa_log_id is not None:
                conn.execute(
                    "update artifacts set message_id = ?, qa_log_id = ? where id = ?",
                    (message_id, qa_log_id, artifact_id),
                )
            else:
                conn.execute(
                    "update artifacts set message_id = ? where id = ?",
                    (message_id, artifact_id),
                )

    @staticmethod
    def format_artifact(art: dict[str, Any]) -> dict[str, Any]:
        """将数据库产物记录转换为前端格式。"""
        kind = art.get("kind", "file")
        is_image = kind == "image"
        artifact_id = art["id"]
        return {
            "id": artifact_id,
            "sessionId": art.get("session_id", ""),
            "messageId": art.get("message_id"),
            "qaLogId": art.get("qa_log_id"),
            "tenantId": art.get("tenant_id", ""),
            "userId": art.get("user_id"),
            "worker": art.get("worker", ""),
            "kind": kind,
            "filename": art.get("filename", ""),
            "mimeType": art.get("mime_type", ""),
            "sizeBytes": art.get("size_bytes", 0),
            "url": f"/api/artifacts/{artifact_id}",
            "previewUrl": f"/api/artifacts/{artifact_id}?preview=1" if is_image else None,
            "createdAt": art.get("created_at", ""),
            "metadata": art.get("metadata", {}),
        }


db = WebDatabase()
