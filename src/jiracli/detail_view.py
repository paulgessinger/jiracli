"""Shared rendering of an issue's detail, used by both the modal detail
screen and the preview sidebar."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.text import Text
from textual.widget import Widget
from textual.widgets import Label, Static

from jiracli.models import IssueDetail
from jiracli.timeutil import absolute, parse_jira_dt

MAX_COMMENTS = 10


def build_detail_widgets(detail: IssueDetail, url: str) -> list[Widget]:
    """Build the list of widgets that render an issue's detail.

    All dynamic content is wrapped in Rich ``Text`` so Textual does not try to
    parse issue text (summaries, descriptions, comments) as console markup.
    """
    s = detail.summary
    title = Text.assemble((s.key, "bold"), "  ", s.summary)
    meta1 = Text.assemble(
        ("Status: ", "dim"), s.status,
        ("   Type: ", "dim"), s.issuetype,
        ("   Priority: ", "dim"), s.priority,
    )
    meta2 = Text.assemble(
        ("Assignee: ", "dim"), s.assignee or "—",
        ("   Reporter: ", "dim"), s.reporter or "—",
    )
    meta3 = Text.assemble(
        ("Created: ", "dim"), absolute(s.created),
        ("   Updated: ", "dim"), absolute(s.updated),
    )
    widgets: list[Widget] = [
        Label(title, classes="detail-title"),
        Static(meta1),
        Static(meta2),
        Static(meta3),
        Static(Text(url, style="dim")),
        Label("[b]Description[/b]", classes="section"),
        Static(
            Text(detail.description)
            if detail.description
            else Text("(no description)", style="dim")
        ),
    ]
    if detail.comments:
        widgets.append(Label("[b]Comments[/b]", classes="section"))
        recent = sorted(
            detail.comments,
            key=lambda c: parse_jira_dt(c.created)
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:MAX_COMMENTS]
        for c in recent:
            header = Text.assemble(
                (c.author, "cyan"), (f" · {absolute(c.created)}", "dim"), "\n"
            )
            header.append(c.body)
            widgets.append(Static(header, classes="comment"))
    return widgets
