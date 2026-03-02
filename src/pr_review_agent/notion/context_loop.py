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
) -> tuple[str, NotionContext | None, str | None]:
    """Interactive loop: present context to user and get confirmation.

    Returns:
        (user_choice, notion_context, user_provided_url)
        - user_choice: "confirmed" | "provide_url" | "partial" | "exit"
        - notion_context: populated if user confirmed
        - user_provided_url: populated if user chose to provide a URL
    """
    if not scored_results:
        console.print(Panel(
            "[bold red]No relevant Notion pages found.[/bold red]\n\n"
            "The agent could not find any Notion pages matching this PR.\n"
            "You can:\n"
            "  [3] Provide a specific Notion page URL\n"
            "  [4] Exit and create a Notion page first",
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
    choice = Prompt.ask(
        "Is this the intent behind this PR?",
        choices=["1", "2", "3", "4"],
        default="1",
    )

    if choice == "1":
        # Confirmed
        context = NotionContext(
            page_id=top.page_id,
            page_url=top.url,
            title=top.title,
            description=top.explanation,
            requirements=top.key_matches,
            raw_content=top.content,
        )
        return "confirmed", context, None

    elif choice == "2":
        # Partial — user wants to enrich the page
        console.print(
            "\n[yellow]Please go to Notion and add more detail to the page, "
            "then press Enter to re-search.[/yellow]"
        )
        input()  # Wait for user
        return "partial", None, None

    elif choice == "3":
        # User provides a URL
        url = Prompt.ask("Paste the Notion page URL")
        return "provide_url", None, url

    else:
        # Exit
        return "exit", None, None


def _prompt_no_results() -> tuple[str, NotionContext | None, str | None]:
    """Handle the case where no results were found."""
    choice = Prompt.ask(
        "Choose an option",
        choices=["3", "4"],
        default="4",
    )

    if choice == "3":
        url = Prompt.ask("Paste the Notion page URL")
        return "provide_url", None, url

    return "exit", None, None


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
