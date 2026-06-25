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
- Background polling (default every 60s) re-flags issues with new activity.
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

| Key             | Action            |
|-----------------|-------------------|
| ↑/↓ · `j`/`k`   | Navigate          |
| `Ctrl+D`/`Ctrl+U` | Page down / up  |
| `g` / `G`       | Top / bottom      |
| Enter · `l`     | Open detail view  |
| `o`             | Open in browser   |
| `r`             | Mark read         |
| `u`             | Mark unread       |
| `R`             | Refresh now       |
| `q`             | Quit              |

In the detail view, `j`/`k` scroll, `Ctrl+D`/`Ctrl+U` page down/up, `g`/`G` jump
to top/bottom, `o` opens the browser, and `esc`/`q` goes back. Comments are shown
newest-first.

## Configuration

- Config file: platform config dir, e.g. `~/.config/jiracli/config.toml`
- Database: platform data dir, e.g. `~/.local/share/jiracli/jiracli.db`
  (macOS: `~/Library/Application Support/jiracli/`)
- `JIRACLI_POLL_SECONDS` / `JIRACLI_URL` env vars override the config file.
