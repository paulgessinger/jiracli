"""Sync watched issues from Jira into the local database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from jiracli.db import Database
from jiracli.jira_client import JiraClient


@dataclass(slots=True)
class SyncResult:
    total: int
    unread: int
    synced_at: str


async def sync_watched(client: JiraClient, db: Database) -> SyncResult:
    """Fetch all watched issues, upsert them, and prune unwatched ones."""
    issues = await client.search_watched()
    for issue in issues:
        await db.upsert_issue(issue, client.browse_url(issue.key))
    await db.set_unwatched([i.key for i in issues])
    await db.commit()

    synced_at = datetime.now(timezone.utc).isoformat()
    await db.set_meta("last_full_sync", synced_at)
    unread = await db.count_unread()
    return SyncResult(total=len(issues), unread=unread, synced_at=synced_at)
