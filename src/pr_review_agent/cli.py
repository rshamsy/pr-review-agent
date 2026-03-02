"""CLI entry point — Typer-based command-line interface."""

from __future__ import annotations

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


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
