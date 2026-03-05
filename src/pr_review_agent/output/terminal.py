"""Rich terminal output for review results."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def display_results(state: dict[str, Any], verbose: bool = False) -> None:
    """Display review results in the terminal using Rich."""
    brief = state.get("review_brief")
    recommendation = state.get("recommendation")
    analysis = state.get("pr_analysis")
    pr_data = state.get("pr_data")

    if not brief or not recommendation:
        console.print("[red]No review results to display.[/red]")
        return

    # Header
    console.print()
    verdict_color = {
        "approve": "green",
        "request_changes": "red",
        "needs_discussion": "yellow",
    }.get(recommendation.verdict, "white")

    console.print(Panel(
        f"[bold]PR #{pr_data.number}: {pr_data.title}[/bold]\n"
        f"Author: {pr_data.author} | Branch: {pr_data.branch}\n"
        f"Classification: {analysis.classification} | "
        f"+{pr_data.additions}/-{pr_data.deletions}",
        title="PR Review Brief",
    ))

    # CI/CD Status
    ci_status = state.get("ci_status", {})
    if ci_status.get("checks"):
        console.print("\n[bold]CI/CD Status:[/bold]")
        for check in ci_status["checks"]:
            icon = {"success": "[green]PASS[/green]", "failure": "[red]FAIL[/red]", "pending": "[yellow]PENDING[/yellow]"}.get(
                check.get("status", ""), "?"
            )
            console.print(f"  {icon} {check.get('name', 'unknown')}")
        console.print()

    # Summary
    console.print(f"[bold]Summary:[/bold] {brief.summary}\n")

    # Intent vs Implementation deltas table
    if brief.deltas:
        table = Table(title="Intent vs Implementation")
        table.add_column("Aspect", style="cyan", no_wrap=True)
        table.add_column("Intended", style="white")
        table.add_column("Implemented", style="white")
        table.add_column("Status", justify="center")

        status_style = {
            "match": "[green]MATCH[/green]",
            "partial": "[yellow]PARTIAL[/yellow]",
            "missing": "[red]MISSING[/red]",
            "extra": "[blue]EXTRA[/blue]",
        }

        for delta in brief.deltas:
            table.add_row(
                delta.aspect,
                delta.intended,
                delta.implemented,
                status_style.get(delta.status, delta.status),
            )

        console.print(table)
        console.print()

    # What was requested vs implemented
    if verbose:
        if brief.what_was_requested:
            console.print("[bold]What Was Requested:[/bold]")
            for item in brief.what_was_requested:
                console.print(f"  - {item}")
            console.print()

        if brief.what_was_implemented:
            console.print("[bold]What Was Implemented:[/bold]")
            for item in brief.what_was_implemented:
                console.print(f"  - {item}")
            console.print()

    # Code analysis summary
    if verbose and analysis:
        console.print("[bold]Code Analysis:[/bold]")
        if analysis.services:
            console.print(f"  Services: {len(analysis.services)}")
        if analysis.api_routes:
            console.print(f"  API Routes: {len(analysis.api_routes)}")
        if analysis.ui_changes:
            console.print(f"  UI Changes: {len(analysis.ui_changes)}")
        if analysis.risks:
            console.print(f"  Risks: {len(analysis.risks)}")
        console.print()

    # Migration details
    if analysis and analysis.migrations:
        console.print("[bold]Migrations:[/bold]")
        for m in analysis.migrations:
            risk_color = {"high": "red", "medium": "yellow", "low": "green"}.get(m.risk_level, "white")
            console.print(f"  [{risk_color}]{m.name}[/{risk_color}] — risk: {m.risk_level}, rollback: {m.rollback_complexity}")
            for op in m.operations:
                destructive_tag = " [red][DESTRUCTIVE][/red]" if op.destructive else ""
                console.print(f"    {op.type} on {op.table}{destructive_tag}")
            for warning in m.warnings:
                console.print(f"    [yellow]! {warning}[/yellow]")
        console.print()

    # Missing tests
    if analysis and analysis.missing_tests:
        console.print("[bold]Missing Tests:[/bold]")
        for t in analysis.missing_tests:
            severity_color = {"critical": "red", "high": "yellow", "medium": "white"}.get(t.severity, "white")
            console.print(f"  [{severity_color}]{t.severity.upper()}[/{severity_color}]: {t.service_file}")
            console.print(f"    Suggested: {t.suggested_test_file}")
        console.print()

    # Positive findings
    if brief.positive_findings:
        console.print("[bold green]Positive Findings:[/bold green]")
        for item in brief.positive_findings:
            console.print(f"  + {item}")
        console.print()

    # Key concerns
    if brief.key_concerns:
        console.print("[bold yellow]Key Concerns:[/bold yellow]")
        for item in brief.key_concerns:
            console.print(f"  ! {item}")
        console.print()

    # Recommendation verdict
    console.print(Panel(
        f"[bold {verdict_color}]{recommendation.verdict.upper().replace('_', ' ')}[/bold {verdict_color}]\n"
        f"LLM confidence: {brief.llm_confidence:.0%}"
        + (_format_blockers(recommendation) if recommendation.blockers else "")
        + (_format_required(recommendation) if recommendation.required else ""),
        title="Recommendation",
        border_style=verdict_color,
    ))

    # Browser testing checklist
    checklist = state.get("testing_checklist", [])
    if checklist:
        from pr_review_agent.analyzers.checklist_generator import format_checklist

        console.print()
        console.print(Panel(format_checklist(checklist), title="Browser Testing Checklist"))


def _format_blockers(rec: Any) -> str:
    lines = "\n\n[bold red]Blockers:[/bold red]"
    for b in rec.blockers:
        lines += f"\n  - {b}"
    return lines


def _format_required(rec: Any) -> str:
    lines = "\n\n[bold yellow]Required:[/bold yellow]"
    for r in rec.required:
        lines += f"\n  - {r}"
    return lines
