"""Stripped-down issue detail view (modal)."""

from __future__ import annotations

import webbrowser
from datetime import datetime, timezone

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Label, LoadingIndicator, Static

from jiracli.db import Database
from jiracli.jira_client import JiraClient, JiraError
from jiracli.models import IssueDetail
from jiracli.timeutil import absolute, parse_jira_dt


class DetailScreen(ModalScreen[None]):
    """Fetches and shows a single issue. Opening it marks the issue read."""

    BINDINGS = [
        Binding("escape,q", "dismiss", "Back"),
        Binding("o", "open_browser", "Open in browser"),
        # vim-style scrolling
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("g", "scroll_home", "Top", show=False),
        Binding("G", "scroll_end", "Bottom", show=False),
        Binding("ctrl+d", "page_down", "Page down", show=False),
        Binding("ctrl+u", "page_up", "Page up", show=False),
    ]

    def __init__(self, key: str, url: str, client: JiraClient, db: Database) -> None:
        super().__init__()
        self._key = key
        self._url = url
        self._client = client
        self._db = db

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="detail-body"):
            yield LoadingIndicator(id="detail-loading")
        yield Footer()

    def on_mount(self) -> None:
        self.load_issue()

    @work(exclusive=True)
    async def load_issue(self) -> None:
        # Opening the detail view counts as "reading".
        await self._db.mark_read(self._key)
        body = self.query_one("#detail-body", VerticalScroll)
        try:
            detail, raw = await self._client.get_issue(self._key)
        except JiraError as e:
            await self.query_one("#detail-loading").remove()
            await body.mount(
                Static(Text.assemble(("Failed to load issue: ", "red"), str(e)))
            )
            return
        await self._db.save_raw(self._key, raw)
        await self.query_one("#detail-loading").remove()
        await self._render_detail(body, detail)

    async def _render_detail(self, body: VerticalScroll, detail: IssueDetail) -> None:
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
        widgets: list[Static] = [
            Label(title, id="detail-title"),
            Static(meta1),
            Static(meta2),
            Static(meta3),
            Static(Text(self._url, style="dim")),
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
                key=lambda c: parse_jira_dt(c.created) or datetime.min.replace(
                    tzinfo=timezone.utc
                ),
                reverse=True,
            )[:10]
            for c in recent:
                header = Text.assemble(
                    (c.author, "cyan"), (f" · {absolute(c.created)}", "dim"), "\n"
                )
                header.append(c.body)
                widgets.append(Static(header, classes="comment"))
        await body.mount_all(widgets)

    def _body(self) -> VerticalScroll:
        return self.query_one("#detail-body", VerticalScroll)

    def action_scroll_down(self) -> None:
        self._body().scroll_down()

    def action_scroll_up(self) -> None:
        self._body().scroll_up()

    def action_scroll_home(self) -> None:
        self._body().scroll_home()

    def action_scroll_end(self) -> None:
        self._body().scroll_end()

    def action_page_down(self) -> None:
        body = self._body()
        body.scroll_relative(y=max(1, body.size.height // 2))

    def action_page_up(self) -> None:
        body = self._body()
        body.scroll_relative(y=-max(1, body.size.height // 2))

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def action_open_browser(self) -> None:
        webbrowser.open(self._url)
        # mark_read already happened on open, but refresh timestamp anyway.
        self.run_worker(self._db.mark_read(self._key))
