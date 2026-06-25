"""Async SQLite persistence for cached issues and read-state.

Unread rule: an issue is unread when it has never been read
(``read_updated IS NULL``) or its Jira ``updated`` timestamp differs from the
value the user last acknowledged (``read_updated``). Marking read simply copies
``updated`` into ``read_updated`` so any later Jira activity re-flags it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from jiracli.models import IssueSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    key            TEXT PRIMARY KEY,
    id             TEXT,
    summary        TEXT,
    status         TEXT,
    issuetype      TEXT,
    priority       TEXT,
    assignee       TEXT,
    reporter       TEXT,
    project        TEXT,
    status_category TEXT,
    url            TEXT,
    created        TEXT,
    updated        TEXT,
    read_updated   TEXT,
    last_read_at   TEXT,
    last_synced_at TEXT,
    watching       INTEGER NOT NULL DEFAULT 1,
    raw_json       TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class IssueRow:
    key: str
    summary: str
    status: str
    status_category: str
    issuetype: str
    priority: str
    assignee: str
    reporter: str
    project: str
    url: str
    updated: str
    created: str
    last_read_at: str | None
    unread: bool


class Database:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @classmethod
    async def connect(cls, path: Path) -> "Database":
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.executescript(SCHEMA)
        await cls._migrate(conn)
        await conn.commit()
        return cls(conn)

    @staticmethod
    async def _migrate(conn: aiosqlite.Connection) -> None:
        """Add columns introduced after the initial schema, if missing."""
        cur = await conn.execute("PRAGMA table_info(issues)")
        columns = {row[1] for row in await cur.fetchall()}
        if "status_category" not in columns:
            await conn.execute("ALTER TABLE issues ADD COLUMN status_category TEXT")

    async def close(self) -> None:
        await self._conn.close()

    async def upsert_issue(self, issue: IssueSummary, url: str) -> None:
        """Insert or update an issue, preserving read-state and raw_json."""
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO issues (
                key, id, summary, status, status_category, issuetype, priority,
                assignee, reporter, project, url, created, updated,
                last_synced_at, watching
            ) VALUES (
                :key, :id, :summary, :status, :status_category, :issuetype,
                :priority, :assignee, :reporter, :project, :url, :created,
                :updated, :now, 1
            )
            ON CONFLICT(key) DO UPDATE SET
                id            = excluded.id,
                summary       = excluded.summary,
                status        = excluded.status,
                status_category = excluded.status_category,
                issuetype     = excluded.issuetype,
                priority      = excluded.priority,
                assignee      = excluded.assignee,
                reporter      = excluded.reporter,
                project       = excluded.project,
                url           = excluded.url,
                created       = excluded.created,
                updated       = excluded.updated,
                last_synced_at= excluded.last_synced_at,
                watching      = 1
            """,
            {
                "key": issue.key,
                "id": issue.id,
                "summary": issue.summary,
                "status": issue.status,
                "issuetype": issue.issuetype,
                "priority": issue.priority,
                "assignee": issue.assignee,
                "reporter": issue.reporter,
                "project": issue.project,
                "status_category": issue.status_category,
                "url": url,
                "created": issue.created,
                "updated": issue.updated,
                "now": now,
            },
        )

    async def set_unwatched(self, watched_keys: list[str]) -> None:
        """Mark every issue not in ``watched_keys`` as no longer watched."""
        await self._conn.execute("UPDATE issues SET watching = 0")
        if watched_keys:
            placeholders = ",".join("?" for _ in watched_keys)
            await self._conn.execute(
                f"UPDATE issues SET watching = 1 WHERE key IN ({placeholders})",
                watched_keys,
            )

    async def commit(self) -> None:
        await self._conn.commit()

    async def list_issues(
        self, hide_read: bool = False, hide_closed: bool = False
    ) -> list[IssueRow]:
        """Watched issues, newest activity first, with computed unread flag.

        ``hide_read`` drops issues with no new activity; ``hide_closed`` drops
        issues whose Jira status category is ``done``.
        """
        clauses = ["watching = 1"]
        if hide_read:
            clauses.append("(read_updated IS NULL OR read_updated <> updated)")
        if hide_closed:
            clauses.append("COALESCE(status_category, '') <> 'done'")
        where = " AND ".join(clauses)
        cur = await self._conn.execute(
            f"""
            SELECT key, summary, status, status_category, issuetype, priority,
                   assignee, reporter, project, url, updated, created,
                   last_read_at,
                   (read_updated IS NULL OR read_updated <> updated) AS unread
            FROM issues
            WHERE {where}
            ORDER BY updated DESC
            """
        )
        rows = await cur.fetchall()
        return [
            IssueRow(
                key=r["key"],
                summary=r["summary"] or "",
                status=r["status"] or "",
                status_category=r["status_category"] or "",
                issuetype=r["issuetype"] or "",
                priority=r["priority"] or "",
                assignee=r["assignee"] or "",
                reporter=r["reporter"] or "",
                project=r["project"] or "",
                url=r["url"] or "",
                updated=r["updated"] or "",
                created=r["created"] or "",
                last_read_at=r["last_read_at"],
                unread=bool(r["unread"]),
            )
            for r in rows
        ]

    async def count_unread(self) -> int:
        cur = await self._conn.execute(
            """
            SELECT COUNT(*) FROM issues
            WHERE watching = 1
              AND (read_updated IS NULL OR read_updated <> updated)
            """
        )
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def mark_read(self, key: str) -> None:
        """Acknowledge the current ``updated`` value for an issue."""
        await self._conn.execute(
            """
            UPDATE issues
            SET read_updated = updated, last_read_at = ?
            WHERE key = ?
            """,
            (_now(), key),
        )
        await self._conn.commit()

    async def mark_read_many(self, keys: list[str]) -> None:
        """Acknowledge the current ``updated`` value for several issues."""
        if not keys:
            return
        now = _now()
        await self._conn.executemany(
            "UPDATE issues SET read_updated = updated, last_read_at = ? WHERE key = ?",
            [(now, key) for key in keys],
        )
        await self._conn.commit()

    async def mark_unread(self, key: str) -> None:
        """Clear the acknowledged state so the issue shows as unread again."""
        await self._conn.execute(
            "UPDATE issues SET read_updated = NULL, last_read_at = NULL WHERE key = ?",
            (key,),
        )
        await self._conn.commit()

    async def save_raw(self, key: str, raw: dict) -> None:
        await self._conn.execute(
            "UPDATE issues SET raw_json = ? WHERE key = ?",
            (json.dumps(raw), key),
        )
        await self._conn.commit()

    async def get_meta(self, key: str) -> str | None:
        cur = await self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self._conn.commit()
