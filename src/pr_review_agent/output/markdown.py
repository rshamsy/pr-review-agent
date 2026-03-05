"""Markdown output formatter for PR review comments."""

from __future__ import annotations

from typing import Any


def format_review_markdown(state: dict[str, Any]) -> str:
    """Format review results as a markdown PR comment."""
    brief = state.get("review_brief")
    recommendation = state.get("recommendation")
    analysis = state.get("pr_analysis")
    pr_data = state.get("pr_data")
    notion_contexts = state.get("notion_contexts", [])

    if not brief or not recommendation:
        return "# PR Review\n\nNo review results available."

    verdict_emoji = {
        "approve": "&#x2705;",
        "request_changes": "&#x274C;",
        "needs_discussion": "&#x1F4AC;",
    }.get(recommendation.verdict, "")

    lines: list[str] = []

    # Header
    lines.append(f"# {verdict_emoji} PR Review: {recommendation.verdict.upper().replace('_', ' ')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(brief.summary)
    lines.append("")

    # CI/CD Status
    ci_status = state.get("ci_status", {})
    if ci_status.get("checks"):
        lines.append("## CI/CD Status")
        for check in ci_status["checks"]:
            icon = {"success": "&#x2705;", "failure": "&#x274C;", "pending": "&#x23F3;"}.get(
                check.get("status", ""), ""
            )
            lines.append(f"- {icon} {check.get('name', 'unknown')}")
        lines.append("")

    # Notion context
    if notion_contexts:
        lines.append("## Feature Intent (from Notion)")
        for notion_context in notion_contexts:
            lines.append(f"**{notion_context.title}**")
            if notion_context.description:
                lines.append(f"\n{notion_context.description}")
            if notion_context.page_url:
                lines.append(f"\n[View in Notion]({notion_context.page_url})")
            lines.append("")

    # What was requested
    if brief.what_was_requested:
        lines.append("## What Was Requested")
        for item in brief.what_was_requested:
            lines.append(f"- {item}")
        lines.append("")

    # What was implemented
    if brief.what_was_implemented:
        lines.append("## What Was Implemented")
        for item in brief.what_was_implemented:
            lines.append(f"- {item}")
        lines.append("")

    # Deltas table
    if brief.deltas:
        lines.append("## Intent vs Implementation")
        lines.append("")
        lines.append("| Aspect | Intended | Implemented | Status |")
        lines.append("|--------|----------|-------------|--------|")
        for delta in brief.deltas:
            status_badge = {
                "match": "MATCH",
                "partial": "PARTIAL",
                "missing": "MISSING",
                "extra": "EXTRA",
            }.get(delta.status, delta.status)
            lines.append(
                f"| {delta.aspect} | {delta.intended} | {delta.implemented} | {status_badge} |"
            )
        lines.append("")

    # Code analysis
    if analysis:
        lines.append("## Code Analysis")
        lines.append(f"- **Classification:** {analysis.classification}")
        lines.append(f"- **Changes:** +{analysis.total_additions}/-{analysis.total_deletions}")
        if analysis.services:
            lines.append(f"- **Services:** {len(analysis.services)} changed")
        if analysis.api_routes:
            lines.append(f"- **API Routes:** {len(analysis.api_routes)} changed")
        if analysis.migrations:
            lines.append(f"- **Migrations:** {len(analysis.migrations)}")
            for m in analysis.migrations:
                lines.append(f"  - **{m.name}** — risk: {m.risk_level}, rollback: {m.rollback_complexity}")
                ops = ", ".join(f"{op.type} on `{op.table}`" for op in m.operations)
                lines.append(f"    - Operations: {ops}")
                if m.warnings:
                    lines.append(f"    - Warnings: {'; '.join(m.warnings)}")
        if analysis.risks:
            lines.append(f"- **Risks:** {len(analysis.risks)} identified")
        lines.append("")

    # Missing tests
    if analysis and analysis.missing_tests:
        lines.append("## Missing Tests")
        for t in analysis.missing_tests:
            lines.append(f"- **{t.severity.upper()}**: `{t.service_file}`")
            lines.append(f"  - Suggested: `{t.suggested_test_file}`")
        lines.append("")

    # Positive findings
    if brief.positive_findings:
        lines.append("## Positive Findings")
        for item in brief.positive_findings:
            lines.append(f"- {item}")
        lines.append("")

    # Key concerns
    if brief.key_concerns:
        lines.append("## Key Concerns")
        for item in brief.key_concerns:
            lines.append(f"- {item}")
        lines.append("")

    # Recommendation
    lines.append("## Recommendation")
    lines.append(f"**{recommendation.verdict.upper().replace('_', ' ')}** (confidence: {brief.llm_confidence:.0%})")
    lines.append("")

    if recommendation.blockers:
        lines.append("### Blockers")
        for b in recommendation.blockers:
            lines.append(f"- {b}")
        lines.append("")

    if recommendation.required:
        lines.append("### Required Changes")
        for r in recommendation.required:
            lines.append(f"- {r}")
        lines.append("")

    if recommendation.suggestions:
        lines.append("### Suggestions")
        for s in recommendation.suggestions:
            lines.append(f"- {s}")
        lines.append("")

    # Browser testing checklist
    checklist = state.get("testing_checklist", [])
    if checklist:
        from pr_review_agent.analyzers.checklist_generator import format_checklist

        lines.append("## Browser Testing Checklist")
        lines.append("")
        lines.append(format_checklist(checklist))

    # Footer
    lines.append("---")
    lines.append("*Generated by [PR Review Agent](https://github.com/pr-review-agent)*")

    return "\n".join(lines)
