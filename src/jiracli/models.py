"""Lightweight data structures parsed from Jira REST responses."""

from __future__ import annotations

from dataclasses import dataclass


def _field_str(fields: dict, name: str, sub: str = "name") -> str:
    """Extract a display string from a possibly-nested/absent Jira field."""
    value = fields.get(name)
    if value is None:
        return ""
    if isinstance(value, dict):
        return value.get(sub) or value.get("displayName") or ""
    return str(value)


@dataclass(slots=True)
class IssueSummary:
    key: str
    id: str
    summary: str
    status: str
    status_category: str
    issuetype: str
    priority: str
    assignee: str
    reporter: str
    project: str
    created: str
    updated: str

    @classmethod
    def from_api(cls, raw: dict) -> "IssueSummary":
        fields = raw.get("fields", {}) or {}
        status_obj = fields.get("status") or {}
        status_category = ""
        if isinstance(status_obj, dict):
            category = status_obj.get("statusCategory") or {}
            if isinstance(category, dict):
                status_category = category.get("key") or ""
        return cls(
            key=raw.get("key", ""),
            id=str(raw.get("id", "")),
            summary=fields.get("summary") or "",
            status=_field_str(fields, "status"),
            status_category=status_category,
            issuetype=_field_str(fields, "issuetype"),
            priority=_field_str(fields, "priority"),
            assignee=_field_str(fields, "assignee", sub="displayName"),
            reporter=_field_str(fields, "reporter", sub="displayName"),
            project=_field_str(fields, "project", sub="key"),
            created=fields.get("created") or "",
            updated=fields.get("updated") or "",
        )


@dataclass(slots=True)
class Comment:
    author: str
    created: str
    body: str


@dataclass(slots=True)
class IssueDetail:
    summary: IssueSummary
    description: str
    comments: list[Comment]

    @classmethod
    def from_api(cls, raw: dict) -> "IssueDetail":
        fields = raw.get("fields", {}) or {}
        comment_block = fields.get("comment") or {}
        comments = [
            Comment(
                author=_field_str(c, "author", sub="displayName"),
                created=c.get("created") or "",
                body=c.get("body") or "",
            )
            for c in (comment_block.get("comments") or [])
        ]
        return cls(
            summary=IssueSummary.from_api(raw),
            description=fields.get("description") or "",
            comments=comments,
        )
