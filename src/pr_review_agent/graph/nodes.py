"""LangGraph node functions — each node performs one step of the review pipeline."""

from __future__ import annotations

import asyncio

from rich.console import Console

from pr_review_agent.analyzers.migration_analyzer import detect_migrations
from pr_review_agent.analyzers.pr_analyzer import analyze_pr
from pr_review_agent.github.comment import post_pr_comment
from pr_review_agent.github.pr_client import fetch_ci_checks, fetch_diff, fetch_pr
from pr_review_agent.graph.state import AgentState
from pr_review_agent.llm.brief_generator import generate_brief, summarize_pr
from pr_review_agent.models.review import ReviewRecommendation
from pr_review_agent.notion.client import NotionMCPClient
from pr_review_agent.notion.context_loop import confirm_context, display_exit_instructions
from pr_review_agent.notion.relevance import score_relevance
from pr_review_agent.notion.search import contextual_search, fetch_page_by_url
from pr_review_agent.output.markdown import format_review_markdown
from pr_review_agent.output.terminal import display_results

console = Console()


def _extract_mcp_error(exc: BaseException) -> str:
    """Extract readable error from MCP SDK ExceptionGroup."""
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            return _extract_mcp_error(sub)
    return str(exc)


def fetch_pr_data(state: AgentState) -> dict:
    """Fetch PR data and diff from GitHub."""
    pr_number = state["pr_number"]
    console.print(f"[bold]Fetching PR #{pr_number}...[/bold]")

    pr_data = fetch_pr(pr_number)
    diff_text = fetch_diff(pr_number)

    ci_status = {}
    try:
        ci = fetch_ci_checks(pr_number)
        ci_status = {"all_passed": ci.all_passed, "checks": [c.model_dump() for c in ci.checks]}
    except Exception:
        pass

    console.print(
        f"  PR: [cyan]{pr_data.title}[/cyan] by {pr_data.author}\n"
        f"  {len(pr_data.files)} files, +{pr_data.additions}/-{pr_data.deletions}"
    )

    return {
        "pr_data": pr_data,
        "diff_text": diff_text,
        "ci_status": ci_status,
        "status": "running",
    }


def summarize_pr_node(state: AgentState) -> dict:
    """Generate a PR summary using Claude for contextual search."""
    console.print("[bold]Summarizing PR for context search...[/bold]")

    model = state.get("model", "claude-sonnet-4-20250514")
    summary = summarize_pr(state["pr_data"], state["diff_text"], model=model)

    console.print(f"  Summary: [dim]{summary}[/dim]")

    return {"pr_summary": summary}


def search_notion_node(state: AgentState) -> dict:
    """Search Notion for relevant pages using the PR summary."""
    console.print("[bold]Searching Notion for relevant context...[/bold]")

    from pr_review_agent.config import get_config
    config = get_config()

    async def _search():
        client = NotionMCPClient(notion_api_key=config.notion_api_key)
        async with client.connect():
            return await contextual_search(client, state["pr_summary"])

    try:
        results = asyncio.run(_search())
    except BaseException as exc:
        msg = _extract_mcp_error(exc)
        console.print(f"[red]Notion MCP error: {msg}[/red]")
        return {"notion_results": [], "error": f"Notion connection failed: {msg}"}

    console.print(f"  Found {len(results)} potential match(es)")

    return {"notion_results": results}


def score_relevance_node(state: AgentState) -> dict:
    """Score relevance of each Notion result against the PR."""
    console.print("[bold]Scoring relevance of Notion pages...[/bold]")

    scores = []
    for result in state.get("notion_results", []):
        scored = score_relevance(
            pr_summary=state["pr_summary"],
            notion_content=result.content,
            notion_page_id=result.page_id,
            notion_title=result.title,
            notion_url=result.url,
        )
        scores.append(scored)
        console.print(f"  [{scored.score}/10] {scored.title}")

    # Sort by score descending
    scores.sort(key=lambda s: s.score, reverse=True)

    return {"relevance_scores": scores}


def confirm_context_node(state: AgentState) -> dict:
    """Interactive: ask user to confirm the Notion context."""
    scores = state.get("relevance_scores", [])
    choice, context, url = confirm_context(scores)

    return {
        "user_confirmation": choice,
        "notion_context": context,
        "user_provided_url": url,
    }


def fetch_specific_page_node(state: AgentState) -> dict:
    """Fetch a specific Notion page when user provides a URL."""
    url = state.get("user_provided_url", "")
    console.print(f"[bold]Fetching Notion page: {url}[/bold]")

    from pr_review_agent.config import get_config
    config = get_config()

    async def _fetch():
        client = NotionMCPClient(notion_api_key=config.notion_api_key)
        async with client.connect():
            return await fetch_page_by_url(client, url)

    try:
        result = _fetch() if not url else asyncio.run(_fetch())
    except BaseException as exc:
        msg = _extract_mcp_error(exc)
        console.print(f"[red]Notion MCP error: {msg}[/red]")
        return {"relevance_scores": [], "error": f"Notion connection failed: {msg}"}

    # Create a RelevanceScore for the user-provided page
    from pr_review_agent.models.notion import RelevanceScore
    scored = score_relevance(
        pr_summary=state["pr_summary"],
        notion_content=result.content if hasattr(result, "content") else "",
        notion_page_id=result.page_id if hasattr(result, "page_id") else "",
        notion_title=result.title if hasattr(result, "title") else "User-provided page",
        notion_url=url,
    )

    return {"relevance_scores": [scored]}


def exit_with_instructions_node(state: AgentState) -> dict:
    """Exit the review with instructions for creating Notion context."""
    display_exit_instructions()
    return {"should_block": True, "status": "blocked"}


def analyze_pr_node(state: AgentState) -> dict:
    """Run automated code analysis on the PR."""
    console.print("[bold]Analyzing PR code changes...[/bold]")

    pr_data = state["pr_data"]
    analysis = analyze_pr(pr_data)

    # Detect migrations from diff
    migrations = detect_migrations(pr_data.files)
    analysis.migrations = migrations

    if state.get("verbose"):
        console.print(f"  Classification: {analysis.classification}")
        console.print(f"  Services: {len(analysis.services)}")
        console.print(f"  API routes: {len(analysis.api_routes)}")
        console.print(f"  UI changes: {len(analysis.ui_changes)}")
        console.print(f"  Migrations: {len(analysis.migrations)}")
        console.print(f"  Risks: {len(analysis.risks)}")
        console.print(f"  Missing tests: {len(analysis.missing_tests)}")

    return {"pr_analysis": analysis}


def generate_llm_brief_node(state: AgentState) -> dict:
    """Generate the review brief using Claude."""
    console.print("[bold]Generating review brief with Claude...[/bold]")

    model = state.get("model", "claude-sonnet-4-20250514")
    brief = generate_brief(
        notion_context=state["notion_context"],
        pr_data=state["pr_data"],
        analysis=state["pr_analysis"],
        diff_text=state["diff_text"],
        model=model,
    )

    console.print(f"  LLM recommendation: {brief.llm_recommendation} (confidence: {brief.llm_confidence})")

    return {"review_brief": brief}


def compute_recommendation_node(state: AgentState) -> dict:
    """Compute final recommendation — automated blockers override LLM."""
    brief = state["review_brief"]
    analysis = state["pr_analysis"]

    blockers: list[str] = []
    required: list[str] = []
    suggestions: list[str] = []

    # Automated blockers
    critical_missing = [t for t in analysis.missing_tests if t.severity == "critical"]
    if critical_missing:
        blockers.append(
            f"{len(critical_missing)} critical service(s) missing tests: "
            + ", ".join(t.service_file for t in critical_missing)
        )

    high_risk_migrations = [m for m in analysis.migrations if m.risk_level == "high"]
    if high_risk_migrations:
        blockers.append(
            f"{len(high_risk_migrations)} high-risk migration(s) detected"
        )

    missing_deltas = [d for d in brief.deltas if d.status == "missing"]
    if missing_deltas:
        blockers.append(
            f"{len(missing_deltas)} requirement(s) from spec not implemented: "
            + ", ".join(d.aspect for d in missing_deltas)
        )

    # Required items from analysis
    for test in analysis.missing_tests:
        if test.severity in ("critical", "high"):
            required.append(f"Add tests for {test.service_file}")

    # Suggestions from brief
    suggestions.extend(brief.key_concerns)

    # Determine verdict
    if blockers:
        verdict = "request_changes"
    elif brief.llm_recommendation == "approve" and not required:
        verdict = "approve"
    elif brief.llm_recommendation == "request_changes":
        verdict = "request_changes"
    else:
        verdict = "needs_discussion"

    recommendation = ReviewRecommendation(
        verdict=verdict,
        blockers=blockers,
        required=required,
        suggestions=suggestions,
    )

    return {"recommendation": recommendation, "should_block": bool(blockers)}


def format_output_node(state: AgentState) -> dict:
    """Format and display the review results."""
    # Display in terminal
    display_results(state, verbose=state.get("verbose", False))

    # Generate markdown
    markdown = format_review_markdown(state)

    # Post to GitHub if requested
    if state.get("post_comment"):
        try:
            post_pr_comment(state["pr_number"], markdown)
            console.print("[green]Review posted to GitHub PR.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to post comment: {e}[/red]")

    return {"markdown_comment": markdown, "status": "complete"}
