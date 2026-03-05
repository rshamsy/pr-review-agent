"""Human-in-the-loop context confirmation loop.

Presents Notion search results to the user and asks them to confirm
whether the extracted context matches the PR's intent.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from pr_review_agent.models.notion import NotionContext, RelevanceScore

console = Console()


def confirm_context(
    scored_results: list[RelevanceScore],
) -> tuple[str, list[NotionContext], str | None]:
    """Interactive loop: present context to user and get confirmation.

    Returns:
        (user_choice, notion_contexts, user_provided_url)
        - user_choice: "confirmed" | "provide_url" | "partial" | "exit"
        - notion_contexts: list of selected NotionContext objects
        - user_provided_url: populated if user chose to provide a URL
    """
    if not scored_results:
        console.print(Panel(
            "[bold red]No relevant Notion pages found.[/bold red]\n\n"
            "The agent could not find any Notion pages matching this PR.\n"
            "You can:\n"
            "  [u] Provide a specific Notion page URL\n"
            "  [x] Exit and create a Notion page first",
            title="No Context Found",
        ))
        return _prompt_no_results()

    # Show top result
    top = scored_results[0]
    console.print()
    console.print(Panel(
        f"[bold]{top.title}[/bold]\n"
        f"Relevance: {top.score}/10\n"
        f"URL: {top.url}\n\n"
        f"[dim]{top.explanation}[/dim]\n\n"
        f"[bold]Key matches:[/bold] {', '.join(top.key_matches) if top.key_matches else 'None identified'}\n"
        f"[bold]Gaps:[/bold] {', '.join(top.gaps) if top.gaps else 'None identified'}\n\n"
        f"[dim]Content preview:[/dim]\n{top.content[:500]}...",
        title="Notion Context Found",
    ))

    # Show other results if available
    if len(scored_results) > 1:
        console.print("\n[dim]Other results:[/dim]")
        for i, result in enumerate(scored_results[1:], 2):
            console.print(f"  {i}. [{result.score}/10] {result.title}")

    console.print()
    console.print(
        "Enter page number(s) to select (e.g. 1 or 1,2), or: "
        "s=re-search, u=provide URL, x=exit"
    )

    while True:
        choice = Prompt.ask("Selection", default="1")
        lower = choice.strip().lower()

        if lower == "s":
            console.print(
                "\n[yellow]Please go to Notion and add more detail to the page, "
                "then press Enter to re-search.[/yellow]"
            )
            input()  # Wait for user
            return "partial", [], None

        if lower == "u":
            url = Prompt.ask("Paste the Notion page URL")
            return "provide_url", [], url

        if lower == "x":
            return "exit", [], None

        # Try to parse as comma-separated numbers
        contexts = _parse_selection(choice, scored_results)
        if contexts is not None:
            return "confirmed", contexts, None

        console.print("[red]Invalid selection. Try again.[/red]")


def _parse_selection(
    raw: str,
    scored_results: list[RelevanceScore],
) -> list[NotionContext] | None:
    """Parse comma-separated indices and build NotionContext list.

    Returns None if any index is invalid (non-integer or out of range).
    """
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None

    contexts: list[NotionContext] = []
    seen: set[int] = set()
    for part in parts:
        try:
            idx = int(part)
        except ValueError:
            return None
        if idx < 1 or idx > len(scored_results):
            return None
        if idx in seen:
            continue
        seen.add(idx)
        result = scored_results[idx - 1]
        contexts.append(NotionContext(
            page_id=result.page_id,
            page_url=result.url,
            title=result.title,
            description=result.explanation,
            requirements=result.key_matches,
            raw_content=result.content,
        ))
    return contexts if contexts else None


def _prompt_no_results() -> tuple[str, list[NotionContext], str | None]:
    """Handle the case where no results were found."""
    while True:
        choice = Prompt.ask("Choose an option (u=provide URL, x=exit)", default="x")
        lower = choice.strip().lower()

        if lower == "u":
            url = Prompt.ask("Paste the Notion page URL")
            return "provide_url", [], url

        if lower == "x":
            return "exit", [], None

        console.print("[red]Invalid choice. Try again.[/red]")


def display_exit_instructions() -> None:
    """Show instructions when user exits without context."""
    console.print(Panel(
        "[bold yellow]Review cannot proceed without Notion context.[/bold yellow]\n\n"
        "Please create a Notion page for this feature with:\n"
        "  1. Feature description — what is being built and why\n"
        "  2. Requirements — specific functional requirements\n"
        "  3. Acceptance criteria — how to verify it works\n\n"
        "Then re-run: [bold]pr-review <PR_NUMBER>[/bold]",
        title="Action Required",
    ))
