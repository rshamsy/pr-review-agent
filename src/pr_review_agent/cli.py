"""CLI entry point — Typer-based command-line interface.

Supports:
  pr-review 42              # Review PR #42 (default command)
  pr-review 42 --post       # Post comment to GitHub
  pr-review 42 --verbose    # Detailed output
  pr-review check-config    # Validate env setup
  pr-review set-env KEY=VAL # Persist an env variable
"""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="pr-review",
    help="AI-driven PR review agent — compares intended vs implemented using Notion context.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def review(
    pr_number: int = typer.Argument(..., help="PR number to review"),
    post: bool = typer.Option(False, "--post", help="Post review comment to GitHub PR"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    model: str = typer.Option(
        "claude-sonnet-4-20250514",
        "--model",
        "-m",
        help="Claude model to use for review",
    ),
) -> None:
    """Review a pull request by comparing Notion intent with implementation."""
    from pr_review_agent.config import get_config, validate_config

    # Validate config first
    errors = validate_config()
    config = get_config()
    # Allow missing gh/npx for the review to proceed if API keys are set
    critical_errors = [e for e in errors if "API_KEY" in e]
    if critical_errors:
        for error in critical_errors:
            console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(code=1)

    # Use model from config if not overridden via CLI
    if model == "claude-sonnet-4-20250514" and config.pr_review_model != "claude-sonnet-4-20250514":
        model = config.pr_review_model

    console.print(f"[bold]Starting review of PR #{pr_number}...[/bold]\n")

    try:
        from pr_review_agent.graph.workflow import build_workflow

        workflow = build_workflow()
        result = workflow.invoke({
            "pr_number": pr_number,
            "verbose": verbose,
            "post_comment": post,
            "model": model,
        })

        if result.get("status") == "blocked":
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)


@app.command(name="check-config")
def check_config() -> None:
    """Validate environment configuration."""
    from pr_review_agent.config import validate_config

    errors = validate_config()

    if not errors:
        console.print("[green]All configuration is valid.[/green]")
    else:
        console.print("[red]Configuration issues found:[/red]")
        for error in errors:
            console.print(f"  [red]- {error}[/red]")
        raise typer.Exit(code=1)


@app.command(name="set-env")
def set_env(
    assignment: str = typer.Argument(
        ...,
        help="KEY=VALUE pair, e.g. NOTION_API_KEY=ntn_xxx",
    ),
) -> None:
    """Persist an environment variable to ~/.config/pr-review-agent/.env."""
    from pr_review_agent.config import update_user_env

    key, sep, value = assignment.partition("=")
    if not sep:
        console.print("[red]Error: expected KEY=VALUE (missing '=' sign)[/red]")
        raise typer.Exit(code=1)

    key = key.strip().upper()
    value = value.strip()

    if not value:
        console.print("[red]Error: value must not be empty[/red]")
        raise typer.Exit(code=1)

    try:
        path = update_user_env(key, value)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Saved {key} to {path}[/green]")


def _rewrite_args() -> None:
    """If the first CLI arg is a bare number, inject 'review' subcommand.

    This allows `pr-review 42` to work as shorthand for `pr-review review 42`.
    """
    if len(sys.argv) > 1 and sys.argv[1] not in ("review", "check-config", "set-env", "--help", "--show-completion", "--install-completion"):
        # Check if first arg looks like a PR number (possibly negative test)
        try:
            int(sys.argv[1])
            sys.argv.insert(1, "review")
        except ValueError:
            pass


def main() -> None:
    """Entry point for the CLI."""
    _rewrite_args()
    app()


if __name__ == "__main__":
    main()
