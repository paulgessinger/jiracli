"""Textual TUI: watched-issue list with background activity polling."""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header

from jiracli.config import Settings, require_token
from jiracli.db import Database, IssueRow
from jiracli.jira_client import JiraClient, JiraError
from jiracli.paths import db_file
from jiracli.sync import sync_watched
from jiracli.timeutil import relative

UNREAD_DOT = "●"


class JiraTUI(App[None]):
    CSS_PATH = "jiracli.tcss"
    TITLE = "jiracli"

    BINDINGS = [
        Binding("enter,l", "open_detail", "Open"),
        Binding("o", "open_browser", "Browser"),
        Binding("r", "mark_read", "Mark read"),
        Binding("R", "refresh_now", "Refresh"),
        Binding("q", "quit", "Quit"),
        # vim-style navigation (hidden from the footer to keep it tidy)
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._db: Database | None = None
        self._client: JiraClient | None = None
        self._row_keys: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        table: DataTable = DataTable(id="issues", cursor_type="row", zebra_stripes=True)
        yield table
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#issues", DataTable)
        table.add_column("", key="unread", width=2)
        table.add_column("Key", key="key", width=14)
        table.add_column("Type", key="type", width=10)
        table.add_column("Status", key="status", width=14)
        table.add_column("Updated", key="updated", width=10)
        table.add_column("Summary", key="summary")

        self._db = await Database.connect(db_file())

        try:
            token = require_token()
        except RuntimeError as e:
            self.sub_title = "no token — run `jiracli configure`"
            self.notify(str(e), severity="error", timeout=10)
            await self.refresh_table()
            return

        self._client = JiraClient(self._settings.url, token)
        await self.refresh_table()
        self.run_sync()
        self.set_interval(self._settings.poll_seconds, self.run_sync)

    async def on_unmount(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        if self._db is not None:
            await self._db.close()

    # --- data -------------------------------------------------------------

    async def refresh_table(self) -> None:
        assert self._db is not None
        rows = await self._db.list_issues()
        table = self.query_one("#issues", DataTable)
        cursor = table.cursor_row
        table.clear()
        self._row_keys = []
        for row in rows:
            table.add_row(*self._render_row(row), key=row.key)
            self._row_keys.append(row.key)
        if rows:
            table.move_cursor(row=min(cursor, len(rows) - 1))
        unread = sum(1 for r in rows if r.unread)
        self.sub_title = f"{len(rows)} watched · {unread} unread"

    def _render_row(self, row: IssueRow) -> tuple[Text, ...]:
        style = "bold" if row.unread else "dim"
        dot = Text(UNREAD_DOT if row.unread else "", style="yellow")
        return (
            dot,
            Text(row.key, style=style),
            Text(row.issuetype, style=style),
            Text(row.status, style=style),
            Text(relative(row.updated), style=style),
            Text(row.summary, style=style),
        )

    @work(exclusive=True, group="sync")
    async def run_sync(self) -> None:
        if self._client is None or self._db is None:
            return
        try:
            result = await sync_watched(self._client, self._db)
        except JiraError as e:
            self.notify(f"Sync failed: {e}", severity="error", timeout=8)
            return
        await self.refresh_table()
        self.sub_title = (
            f"{result.total} watched · {result.unread} unread · "
            f"synced {relative(result.synced_at)}"
        )

    # --- helpers ----------------------------------------------------------

    def _current_key(self) -> str | None:
        table = self.query_one("#issues", DataTable)
        if not self._row_keys:
            return None
        idx = table.cursor_row
        if 0 <= idx < len(self._row_keys):
            return self._row_keys[idx]
        return None

    def _current_url(self) -> str | None:
        key = self._current_key()
        if key is None or self._client is None:
            return None
        return self._client.browse_url(key)

    # --- events -----------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter on a row is consumed by DataTable as a selection event.
        self.action_open_detail()

    # --- actions ----------------------------------------------------------

    def action_open_detail(self) -> None:
        key = self._current_key()
        if key is None or self._client is None or self._db is None:
            return
        from jiracli.screens.detail_screen import DetailScreen

        def _on_closed(_result: None) -> None:
            self.run_worker(self.refresh_table())

        self.push_screen(
            DetailScreen(key, self._client.browse_url(key), self._client, self._db),
            _on_closed,
        )

    async def action_open_browser(self) -> None:
        key = self._current_key()
        url = self._current_url()
        if key is None or url is None or self._db is None:
            return
        webbrowser.open(url)
        await self._db.mark_read(key)
        await self.refresh_table()

    async def action_mark_read(self) -> None:
        key = self._current_key()
        if key is None or self._db is None:
            return
        await self._db.mark_read(key)
        await self.refresh_table()

    async def action_refresh_now(self) -> None:
        self.run_sync()

    def action_cursor_down(self) -> None:
        self.query_one("#issues", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#issues", DataTable).action_cursor_up()

    def action_cursor_top(self) -> None:
        self.query_one("#issues", DataTable).move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one("#issues", DataTable)
        if table.row_count:
            table.move_cursor(row=table.row_count - 1)


def run(settings: Settings) -> None:
    JiraTUI(settings).run()
