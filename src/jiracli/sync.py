"""Sync watched issues from Jira into the local database."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from jiracli.db import Database
from jiracli.jira_client import JiraClient
from jiracli.models import IssueSummary


@dataclass(slots=True)
class SyncResult:
    total: int
    unread: int
    synced_at: str
    # Issues that were previously read and gained new activity in this sync
    # (i.e. transitioned read -> unread). Brand-new watched issues are excluded.
    newly_unread: list[IssueSummary] = field(default_factory=list)


async def sync_watched(client: JiraClient, db: Database) -> SyncResult:
    """Fetch all watched issues, upsert them, and prune unwatched ones."""
    issues = await client.search_watched()

    # Snapshot read-state before upserting so we can detect read -> unread.
    prior = await db.read_state()
    newly_unread: list[IssueSummary] = []
    for issue in issues:
        prev = prior.get(issue.key)
        if prev is not None:
            read_updated, prev_updated = prev
            was_unread = read_updated is None or read_updated != prev_updated
            now_unread = read_updated is None or read_updated != issue.updated
            if not was_unread and now_unread:
                newly_unread.append(issue)
        await db.upsert_issue(issue, client.browse_url(issue.key))
    await db.set_unwatched([i.key for i in issues])
    await db.commit()

    synced_at = datetime.now(timezone.utc).isoformat()
    await db.set_meta("last_full_sync", synced_at)
    unread = await db.count_unread()
    return SyncResult(
        total=len(issues),
        unread=unread,
        synced_at=synced_at,
        newly_unread=newly_unread,
    )
