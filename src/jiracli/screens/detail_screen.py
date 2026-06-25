"""Stripped-down issue detail view (modal)."""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, LoadingIndicator, Static

from jiracli.db import Database
from jiracli.detail_view import build_detail_widgets
from jiracli.jira_client import JiraClient, JiraError


class DetailScreen(ModalScreen[None]):
    """Fetches and shows a single issue. Opening it marks the issue read."""

    BINDINGS = [
        Binding("escape,q,h", "dismiss", "Back"),
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
        await body.mount_all(build_detail_widgets(detail, self._url))

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
