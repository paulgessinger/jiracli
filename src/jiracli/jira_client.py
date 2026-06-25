"""Async Jira Server/Data Center REST client (thin, httpx-based).

Only the small surface jiracli needs: identity check, watched-issue search,
and full issue fetch. Authenticates with a Personal Access Token via the
``Authorization: Bearer`` header.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from jiracli.models import IssueDetail, IssueSummary

# Light fields fetched for the list view.
LIST_FIELDS = (
    "summary,status,updated,created,assignee,reporter,priority,issuetype,project"
)
# Fields fetched for the detail view.
DETAIL_FIELDS = LIST_FIELDS + ",description,comment"

WATCHED_JQL = "watcher = currentUser() ORDER BY updated DESC"


class JiraError(Exception):
    """Raised for Jira API / network failures with a user-facing message."""


class JiraClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    async def __aenter__(self) -> "JiraClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> dict:
        try:
            resp = await self._client.get(path, params=params or None)
        except httpx.HTTPError as e:
            raise JiraError(f"Network error talking to Jira: {e}") from e
        if resp.status_code == 401:
            raise JiraError("Authentication failed (401): token invalid or expired.")
        if resp.status_code == 403:
            raise JiraError("Access forbidden (403): token lacks permission.")
        if resp.status_code >= 400:
            raise JiraError(
                f"Jira returned HTTP {resp.status_code} for {path}: {resp.text[:200]}"
            )
        return resp.json()

    def browse_url(self, key: str) -> str:
        return f"{self.base_url}/browse/{key}"

    async def myself(self) -> dict:
        """Return the authenticated user (connection/auth check)."""
        return await self._get("/rest/api/2/myself")

    async def search_watched(self, page_size: int = 50) -> list[IssueSummary]:
        """Return all issues the current user watches, newest activity first."""
        issues: list[IssueSummary] = []
        start_at = 0
        while True:
            data = await self._get(
                "/rest/api/2/search",
                jql=WATCHED_JQL,
                fields=LIST_FIELDS,
                startAt=start_at,
                maxResults=page_size,
            )
            batch = data.get("issues", []) or []
            issues.extend(IssueSummary.from_api(raw) for raw in batch)
            total = data.get("total", len(issues))
            start_at += len(batch)
            if not batch or start_at >= total:
                break
        return issues

    async def get_issue(self, key: str) -> tuple[IssueDetail, dict]:
        """Return parsed detail plus the raw JSON for caching."""
        raw = await self._get(f"/rest/api/2/issue/{key}", fields=DETAIL_FIELDS)
        return IssueDetail.from_api(raw), raw
