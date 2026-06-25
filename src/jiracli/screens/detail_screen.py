"""Stripped-down issue detail view (modal)."""

from __future__ import annotations

import webbrowser

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Label, LoadingIndicator, Static

from jiracli.db import Database
from jiracli.jira_client import JiraClient, JiraError
from jiracli.models import IssueDetail
from jiracli.timeutil import absolute


class DetailScreen(ModalScreen[None]):
    """Fetches and shows a single issue. Opening it marks the issue read."""

    BINDINGS = [
        Binding("escape,q", "dismiss", "Back"),
        Binding("o", "open_browser", "Open in browser"),
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
            await body.mount(Static(f"[red]Failed to load issue:[/red] {e}"))
            return
        await self._db.save_raw(self._key, raw)
        await self.query_one("#detail-loading").remove()
        await self._render_detail(body, detail)

    async def _render_detail(self, body: VerticalScroll, detail: IssueDetail) -> None:
        s = detail.summary
        widgets: list[Static] = [
            Label(f"[b]{s.key}[/b]  {s.summary}", id="detail-title"),
            Static(
                f"[dim]Status:[/dim] {s.status}   "
                f"[dim]Type:[/dim] {s.issuetype}   "
                f"[dim]Priority:[/dim] {s.priority}"
            ),
            Static(
                f"[dim]Assignee:[/dim] {s.assignee or '—'}   "
                f"[dim]Reporter:[/dim] {s.reporter or '—'}"
            ),
            Static(
                f"[dim]Created:[/dim] {absolute(s.created)}   "
                f"[dim]Updated:[/dim] {absolute(s.updated)}"
            ),
            Static(f"[dim]{self._url}[/dim]"),
            Label("[b]Description[/b]", classes="section"),
            Static(detail.description or "[dim](no description)[/dim]"),
        ]
        if detail.comments:
            widgets.append(Label("[b]Comments[/b]", classes="section"))
            for c in detail.comments[-10:]:
                widgets.append(
                    Static(
                        f"[cyan]{c.author}[/cyan] [dim]· {absolute(c.created)}[/dim]\n"
                        f"{c.body}",
                        classes="comment",
                    )
                )
        await body.mount_all(widgets)

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def action_open_browser(self) -> None:
        webbrowser.open(self._url)
        # mark_read already happened on open, but refresh timestamp anyway.
        self.run_worker(self._db.mark_read(self._key))
