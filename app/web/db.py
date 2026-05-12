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
    """Small SQLite persistence layer for the Web MVP."""

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
                    role text not null default 'employee',
                    enabled integer not null default 1,
                    created_at text not null
                );

                create table if not exists chat_sessions (
                    id text primary key,
                    user_id integer not null,
                    title text not null,
                    created_at text not null,
                    updated_at text not null,
                    foreign key(user_id) references users(id)
                );

                create table if not exists messages (
                    id integer primary key autoincrement,
                    session_id text not null,
                    user_id integer not null,
                    role text not null,
                    content text not null,
                    created_at text not null,
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
                    created_at text not null
                );

                create table if not exists documents (
                    id text primary key,
                    source text not null,
                    uploaded_by integer,
                    status text not null,
                    chunks integer not null default 0,
                    entities integer not null default 0,
                    relationships integer not null default 0,
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists feedback (
                    id integer primary key autoincrement,
                    qa_log_id integer not null,
                    user_id integer not null,
                    rating integer not null,
                    comment text not null default '',
                    created_at text not null,
                    foreign key(qa_log_id) references qa_logs(id),
                    foreign key(user_id) references users(id)
                );
                """
            )
            self._ensure_column(conn, "users", "enabled", "integer not null default 1")

    def create_user(self, username: str, password_hash: str, role: str = "employee") -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                "insert into users(username, password_hash, role, enabled, created_at) values (?, ?, ?, ?, ?)",
                (username, password_hash, role, 1, utc_now()),
            )
            return self.get_user_by_id(cur.lastrowid, conn=conn)

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select id, username, role, enabled, created_at
                from users
                order by id asc
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def update_user(self, user_id: int, role: str | None = None, enabled: bool | None = None) -> dict[str, Any] | None:
        updates = []
        params: list[Any] = []
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        if not updates:
            return self.get_user_by_id(user_id)
        params.append(user_id)
        with self.connect() as conn:
            conn.execute(f"update users set {', '.join(updates)} where id = ?", params)
            return self.get_user_by_id(user_id, conn=conn)

    def count_users(self) -> int:
        with self.connect() as conn:
            row = conn.execute("select count(*) as total from users").fetchone()
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

    def create_session(self, user_id: int, session_id: str, title: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "insert into chat_sessions(id, user_id, title, created_at, updated_at) values (?, ?, ?, ?, ?)",
                (session_id, user_id, title, now, now),
            )
        return {"id": session_id, "user_id": user_id, "title": title, "created_at": now, "updated_at": now}

    def ensure_session(self, user_id: int, session_id: str, title: str) -> dict[str, Any]:
        session = self.get_session(user_id, session_id)
        if session:
            return session
        return self.create_session(user_id, session_id, title)

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

    def add_message(self, session_id: str, user_id: int, role: str, content: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                "insert into messages(session_id, user_id, role, content, created_at) values (?, ?, ?, ?, ?)",
                (session_id, user_id, role, content, now),
            )
            conn.execute(
                "update chat_sessions set updated_at = ? where id = ? and user_id = ?",
                (now, session_id, user_id),
            )
            return {"id": cur.lastrowid, "session_id": session_id, "role": role, "content": content, "created_at": now}

    def list_messages(self, session_id: str, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from messages
                where session_id = ? and user_id = ?
                order by id desc
                limit ?
                """,
                (session_id, user_id, limit),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]

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
    ) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into qa_logs(
                    session_id, user_id, question, answer, workers, dispatch_reasoning,
                    worker_results, confidence, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            return {"id": cur.lastrowid}

    def list_qa_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("select * from qa_logs order by id desc limit ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def upsert_document(self, doc: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                insert into documents(id, source, uploaded_by, status, chunks, entities, relationships, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    source = excluded.source,
                    uploaded_by = excluded.uploaded_by,
                    status = excluded.status,
                    chunks = excluded.chunks,
                    entities = excluded.entities,
                    relationships = excluded.relationships,
                    updated_at = excluded.updated_at
                """,
                (
                    doc["id"],
                    doc.get("source", ""),
                    doc.get("uploaded_by"),
                    doc.get("status", "ready"),
                    doc.get("chunks", 0),
                    doc.get("entities", 0),
                    doc.get("relationships", 0),
                    doc.get("created_at", now),
                    now,
                ),
            )

    def delete_document_record(self, doc_id: str) -> None:
        with self.connect() as conn:
            conn.execute("delete from documents where id = ?", (doc_id,))

    def list_document_records(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("select * from documents order by updated_at desc").fetchall()
            return [dict(row) for row in rows]

    def add_feedback(self, qa_log_id: int, user_id: int, rating: int, comment: str = "") -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                "insert into feedback(qa_log_id, user_id, rating, comment, created_at) values (?, ?, ?, ?, ?)",
                (qa_log_id, user_id, rating, comment, utc_now()),
            )
            return {"id": cur.lastrowid}

    def list_hard_cases(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
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

    def list_knowledge_gaps(self, limit: int = 20) -> list[dict[str, Any]]:
        cases = self.list_hard_cases(limit=500)
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
                    "reasons": {
                        "not_found": 0,
                        "low_confidence": 0,
                        "negative_feedback": 0,
                    },
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
                item["examples"].append(
                    {
                        "id": case.get("id"),
                        "question": question,
                        "answer": case.get("answer", ""),
                        "comment": case.get("comment", ""),
                    }
                )

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


db = WebDatabase()
