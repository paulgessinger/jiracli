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
        Binding("space", "toggle_select", "Select"),
        Binding("r", "mark_read", "Mark read"),
        Binding("u", "mark_unread", "Mark unread"),
        Binding("m", "mark_older_read", "Read ≤ here"),
        Binding("R", "refresh_now", "Refresh"),
        Binding("q", "quit", "Quit"),
        # vim-style navigation (hidden from the footer to keep it tidy)
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("ctrl+d", "page_down", "Page down", show=False),
        Binding("ctrl+u", "page_up", "Page up", show=False),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._db: Database | None = None
        self._client: JiraClient | None = None
        self._row_keys: list[str] = []
        self._rows: dict[str, IssueRow] = {}
        self._selected: set[str] = set()

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
            self.notify(str(e), severity="error", timeout=10, markup=False)
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
        scroll_y = table.scroll_offset.y
        table.clear()
        self._row_keys = []
        self._rows = {}
        for row in rows:
            table.add_row(*self._render_row(row), key=row.key)
            self._row_keys.append(row.key)
            self._rows[row.key] = row
        # Drop selections for issues that are no longer present.
        self._selected &= set(self._rows)
        if rows:
            table.move_cursor(row=min(cursor, len(rows) - 1), scroll=False)
            table.scroll_to(y=scroll_y, animate=False)
        self._update_subtitle()

    def _update_subtitle(self) -> None:
        total = len(self._rows)
        unread = sum(1 for r in self._rows.values() if r.unread)
        suffix = f" · {len(self._selected)} selected" if self._selected else ""
        self.sub_title = f"{total} watched · {unread} unread{suffix}"

    def _render_row(self, row: IssueRow) -> tuple[Text, ...]:
        style = "bold" if row.unread else "dim"
        if row.key in self._selected:
            style += " reverse"
        dot = Text(UNREAD_DOT if row.unread else "", style="yellow")
        return (
            dot,
            Text(row.key, style=style),
            Text(row.issuetype, style=style),
            Text(row.status, style=style),
            Text(relative(row.updated), style=style),
            Text(row.summary, style=style),
        )

    _COLUMN_KEYS = ("unread", "key", "type", "status", "updated", "summary")

    def _update_row(self, key: str) -> None:
        """Re-render a single row in place (no clear/rebuild, no scroll jump)."""
        row = self._rows.get(key)
        if row is None:
            return
        table = self.query_one("#issues", DataTable)
        for column_key, value in zip(self._COLUMN_KEYS, self._render_row(row)):
            table.update_cell(key, column_key, value, update_width=False)

    @work(exclusive=True, group="sync")
    async def run_sync(self) -> None:
        if self._client is None or self._db is None:
            return
        try:
            result = await sync_watched(self._client, self._db)
        except JiraError as e:
            self.notify(f"Sync failed: {e}", severity="error", timeout=8, markup=False)
            return
        await self.refresh_table()
        suffix = f" · {len(self._selected)} selected" if self._selected else ""
        self.sub_title = (
            f"{result.total} watched · {result.unread} unread{suffix} · "
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
        self._set_unread(key, False)

    def _target_keys(self) -> list[str]:
        """Selected issues if any, otherwise the issue under the cursor."""
        if self._selected:
            return [k for k in self._row_keys if k in self._selected]
        key = self._current_key()
        return [key] if key is not None else []

    def _set_unread(self, key: str, unread: bool) -> None:
        """Update cached unread state and re-render that row in place."""
        row = self._rows.get(key)
        if row is not None:
            row.unread = unread
        self._update_row(key)

    async def action_mark_read(self) -> None:
        if self._db is None:
            return
        keys = self._target_keys()
        if not keys:
            return
        await self._db.mark_read_many(keys)
        self._selected.clear()
        for key in keys:
            self._set_unread(key, False)
        self._update_subtitle()

    async def action_mark_unread(self) -> None:
        if self._db is None:
            return
        keys = self._target_keys()
        if not keys:
            return
        for key in keys:
            await self._db.mark_unread(key)
        self._selected.clear()
        for key in keys:
            self._set_unread(key, True)
        self._update_subtitle()

    async def action_mark_older_read(self) -> None:
        """Mark the selected issue and everything older (below it) as read."""
        if self._db is None:
            return
        table = self.query_one("#issues", DataTable)
        idx = table.cursor_row
        if not (0 <= idx < len(self._row_keys)):
            return
        keys = self._row_keys[idx:]
        await self._db.mark_read_many(keys)
        for key in keys:
            self._set_unread(key, False)
        self._update_subtitle()

    def action_toggle_select(self) -> None:
        key = self._current_key()
        if key is None:
            return
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        self._update_row(key)
        self._update_subtitle()
        # Advance the cursor for quick consecutive selection.
        self.query_one("#issues", DataTable).action_cursor_down()

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

    def _half_page(self) -> int:
        table = self.query_one("#issues", DataTable)
        return max(1, table.size.height // 2)

    def action_page_down(self) -> None:
        table = self.query_one("#issues", DataTable)
        if table.row_count:
            target = min(table.cursor_row + self._half_page(), table.row_count - 1)
            table.move_cursor(row=target)

    def action_page_up(self) -> None:
        table = self.query_one("#issues", DataTable)
        if table.row_count:
            target = max(table.cursor_row - self._half_page(), 0)
            table.move_cursor(row=target)


def run(settings: Settings) -> None:
    JiraTUI(settings).run()
