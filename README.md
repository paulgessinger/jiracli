# jiracli

A terminal (Textual) dashboard for the Jira issues you **watch** on CERN's
self-hosted Jira (`https://its.cern.ch/jira`, a Jira Server/Data Center
instance). It caches your watched issues in a local SQLite database and shows,
at a glance, which ones have had new activity since you last read them.

## Features

- Pulls every issue you watch (`watcher = currentUser()`), newest activity first.
- Local SQLite cache in your OS data directory.
- **Unread** indicator (`●`) per issue; an issue becomes unread again whenever
  Jira activity changes its `updated` timestamp.
- Detail view (description + recent comments) and "open in browser".
- Background polling (default every 60s) re-flags issues with new activity, and
  sends a **desktop notification** when a previously-read issue gains activity.
- An issue is considered **read** when you mark it read in the list, open its
  detail view, or open it in the browser.

## Setup

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run jiracli configure
```

`configure` asks for:
- the Jira URL (defaults to `https://its.cern.ch/jira`),
- a **Personal Access Token** (create one in Jira → profile → *Personal Access
  Tokens*),
- the poll interval.

The URL and interval are saved to `config.toml` (validated with pydantic). The
token is stored in your **OS keyring** — it is never written to the config file.
You can alternatively provide the token via the `JIRA_PAT` environment variable.

## Usage

```bash
uv run jiracli          # launch the TUI (default)
uv run jiracli sync     # one-off headless sync into the DB
uv run jiracli configure
```

### Keys (TUI)

| Key             | Action                                   |
|-----------------|------------------------------------------|
| ↑/↓ · `j`/`k`   | Navigate                                 |
| `Ctrl+D`/`Ctrl+U` | Page down / up                         |
| `g` / `G`       | Top / bottom                             |
| `Space`         | Toggle selection (multi-select)          |
| Enter · `l`     | Open detail view                         |
| `o`             | Open in browser                          |
| `r`             | Mark read (selection if any, else row)   |
| `u`             | Mark unread (selection if any, else row) |
| `m`             | Mark selected row **and older** as read  |
| `f`             | Toggle hide **read** issues              |
| `c`             | Toggle hide **closed** issues            |
| `s`             | Toggle the preview **sidebar**           |
| `R`             | Refresh now                              |
| `q`             | Quit                                     |

Select issues with `Space` (selected rows are highlighted), then `r`/`u` act on
the whole selection at once. With no selection, `r`/`u` act on the row under the
cursor. `m` marks the current row plus everything older than it (lower in the
list) as read.

`f` hides issues with no new activity (read), and `c` hides closed issues
(Jira status category *done*). Both filters are **remembered between runs**
(stored in the local database), and the active filters are shown in the title
bar.

`s` toggles a preview **sidebar** on the right that shows the detail of whichever
issue is currently highlighted, updating as you move the cursor. The sidebar is a
read-only preview — unlike opening the modal detail view, hovering an issue in
the sidebar does **not** mark it as read. Its visibility is also remembered
between runs.

In the detail view, `j`/`k` scroll, `Ctrl+D`/`Ctrl+U` page down/up, `g`/`G` jump
to top/bottom, `o` opens the browser, and `esc`/`q`/`h` goes back. Comments are
shown newest-first.

## Configuration

- Config file: platform config dir, e.g. `~/.config/jiracli/config.toml`
- Database: platform data dir, e.g. `~/.local/share/jiracli/jiracli.db`
  (macOS: `~/Library/Application Support/jiracli/`)
- `JIRACLI_POLL_SECONDS` / `JIRACLI_URL` env vars override the config file.

### Notifications

When a watched issue you'd already read gains new activity during a background
sync, jiracli sends a desktop notification (interactive actions and the first
sync at startup never notify).

Notifications use the **OSC 9 terminal escape sequence** (`ESC ] 9 ; … BEL`),
which is understood by Ghostty, kitty, WezTerm and iTerm2. It needs no
subprocess and works over SSH — the notification appears on the machine running
the terminal emulator. Terminals without OSC 9 support simply ignore it.

- `notifications = true|false` in `config.toml` — on/off switch.
- Run **"Send test notification"** from the command palette (`Ctrl+P`) to verify
  your setup; it warns if your terminal isn't a known OSC 9 one.
