"""Command-line entry point for jiracli."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from jiracli import app as tui
from jiracli.config import (
    DEFAULT_URL,
    get_token,
    load_settings,
    save_settings,
    save_token,
)
from jiracli.db import Database
from jiracli.jira_client import JiraClient, JiraError
from jiracli.paths import config_file, db_file
from jiracli.sync import sync_watched

cli = typer.Typer(
    help="Terminal dashboard for your watched CERN Jira issues.",
    no_args_is_help=False,
    add_completion=False,
)


@cli.command()
def configure(
    url: Annotated[
        str,
        typer.Option(help="Base URL of the Jira instance."),
    ] = DEFAULT_URL,
    poll_seconds: Annotated[
        int,
        typer.Option(help="Background poll interval (seconds)."),
    ] = 60,
) -> None:
    """Store the Jira URL/interval and a Personal Access Token, then verify."""
    url = typer.prompt("Jira URL", default=url)
    token = typer.prompt("Personal Access Token", hide_input=True)
    poll_seconds = typer.prompt("Poll interval (seconds)", default=poll_seconds, type=int)

    save_settings(url, poll_seconds)
    save_token(token)
    typer.echo(f"Saved config to {config_file()}")

    async def _verify() -> dict:
        async with JiraClient(url, token) as client:
            return await client.myself()

    try:
        me = asyncio.run(_verify())
    except JiraError as e:
        typer.secho(f"Verification failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    name = me.get("displayName") or me.get("name") or "unknown"
    typer.secho(f"Authenticated as {name}.", fg=typer.colors.GREEN)


@cli.command()
def sync() -> None:
    """Run a one-off headless sync of watched issues into the local DB."""
    settings = load_settings()
    token = get_token()
    if not token:
        typer.secho(
            "No token. Run `jiracli configure` or set JIRA_PAT.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    async def _run() -> None:
        db = await Database.connect(db_file())
        try:
            async with JiraClient(settings.url, token) as client:
                result = await sync_watched(client, db)
        finally:
            await db.close()
        typer.echo(
            f"Synced {result.total} watched issues ({result.unread} unread)."
        )

    try:
        asyncio.run(_run())
    except JiraError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


@cli.command()
def run() -> None:
    """Launch the TUI (default command)."""
    settings = load_settings()
    tui.run(settings)


@cli.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Launch the TUI when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        run()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
