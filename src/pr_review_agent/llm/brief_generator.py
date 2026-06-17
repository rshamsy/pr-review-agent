"""LLM brief generator — uses Claude to compare intent vs implementation."""

from __future__ import annotations

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from pr_review_agent.analyzers.role_detector import RoleDetectionResult
from pr_review_agent.llm.prompts import (
    REVIEW_BRIEF_SYSTEM,
    REVIEW_BRIEF_USER,
    ROLE_TESTING_SYSTEM,
    ROLE_TESTING_USER,
    SUMMARIZE_PR_SYSTEM,
    SUMMARIZE_PR_USER,
)
from pr_review_agent.models.brief import ReviewBrief
from pr_review_agent.models.notion import NotionContext
from pr_review_agent.models.pr import PRAnalysis, PRData
from pr_review_agent.models.review import RoleTestingPathway

MAX_DIFF_CHARS = 80_000


def summarize_pr(pr_data: PRData, diff_text: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Generate a 1-2 sentence summary of the PR for contextual Notion search."""
    llm = ChatAnthropic(model=model, max_tokens=256, temperature=0)

    diff_preview = diff_text[:4000]

    user_msg = SUMMARIZE_PR_USER.format(
        pr_number=pr_data.number,
        pr_title=pr_data.title,
        branch=pr_data.branch,
        author=pr_data.author,
        file_count=len(pr_data.files),
        additions=pr_data.additions,
        deletions=pr_data.deletions,
        diff_preview=diff_preview,
    )

    response = llm.invoke([
        SystemMessage(content=SUMMARIZE_PR_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    return response.content if isinstance(response.content, str) else str(response.content)


def generate_brief(
    notion_contexts: list[NotionContext],
    pr_data: PRData,
    analysis: PRAnalysis,
    diff_text: str,
    ci_status: dict | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> ReviewBrief:
    """Generate a structured review brief comparing intent vs implementation."""
    llm = ChatAnthropic(model=model, max_tokens=4096, temperature=0)

    # Truncate diff to stay within token limits
    truncated_diff = diff_text[:MAX_DIFF_CHARS]
    if len(diff_text) > MAX_DIFF_CHARS:
        truncated_diff += f"\n\n... (truncated, {len(diff_text) - MAX_DIFF_CHARS} chars omitted)"

    user_msg = REVIEW_BRIEF_USER.format(
        notion_section=_format_notion_contexts(notion_contexts),
        ci_status_summary=_format_ci_status(ci_status or {}),
        classification=analysis.classification,
        services_summary=_format_services(analysis),
        api_routes_summary=_format_api_routes(analysis),
        ui_changes_summary=_format_ui_changes(analysis),
        migrations_summary=_format_migrations(analysis),
        missing_tests_summary=_format_missing_tests(analysis),
        risks_summary=_format_risks(analysis),
        diff_text=truncated_diff,
    )

    response = llm.invoke([
        SystemMessage(content=REVIEW_BRIEF_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    content = response.content if isinstance(response.content, str) else str(response.content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
        else:
            return ReviewBrief(
                summary="Failed to parse LLM response",
                llm_recommendation="needs_discussion",
                llm_confidence=0.0,
                key_concerns=["LLM response parsing failed"],
            )

    return ReviewBrief(**data)


def generate_role_testing(
    detection: RoleDetectionResult,
    notion_contexts: list[NotionContext],
    analysis: PRAnalysis,
    model: str = "claude-sonnet-4-20250514",
) -> list[RoleTestingPathway]:
    """Generate role-based testing pathways using Claude."""
    llm = ChatAnthropic(model=model, max_tokens=4096, temperature=0)

    # Build notion summary
    notion_parts: list[str] = []
    for ctx in notion_contexts:
        notion_parts.append(f"- {ctx.title}: {ctx.description}")
    notion_summary = "\n".join(notion_parts) if notion_parts else "No Notion context available."

    # Build route/page lists
    api_routes = "\n".join(
        f"- {r.endpoint} ({', '.join(r.methods)})" for r in analysis.api_routes
    ) or "None"
    ui_pages = "\n".join(
        f"- {u.path} ({'new' if u.is_new else 'modified'} {u.type})" for u in analysis.ui_changes
    ) or "None"

    # Truncate snippets to stay within limits
    snippets_text = "\n\n---\n\n".join(detection.role_snippets[:15])
    if len(snippets_text) > 20_000:
        snippets_text = snippets_text[:20_000] + "\n\n... (truncated)"

    user_msg = ROLE_TESTING_USER.format(
        detected_roles=", ".join(detection.detected_roles) or "None explicitly detected",
        auth_patterns=", ".join(detection.auth_patterns) or "None",
        role_snippets=snippets_text,
        notion_summary=notion_summary,
        api_routes=api_routes,
        ui_pages=ui_pages,
    )

    try:
        response = llm.invoke([
            SystemMessage(content=ROLE_TESTING_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(content[start:end])
            else:
                return []

        return [RoleTestingPathway(**p) for p in data.get("pathways", [])]
    except Exception:
        return []


def _format_notion_contexts(contexts: list[NotionContext]) -> str:
    """Format one or more NotionContext objects for the prompt."""
    if not contexts:
        return "No Notion context provided."

    if len(contexts) == 1:
        ctx = contexts[0]
        return (
            f"Title: {ctx.title}\n"
            f"Description: {ctx.description}\n"
            f"Requirements:\n{_format_list(ctx.requirements)}"
        )

    parts: list[str] = []
    for i, ctx in enumerate(contexts, 1):
        parts.append(
            f"### Page {i}: {ctx.title}\n"
            f"Description: {ctx.description}\n"
            f"Requirements:\n{_format_list(ctx.requirements)}"
        )
    return "\n\n".join(parts)


def _format_list(items: list[str]) -> str:
    if not items:
        return "None specified"
    return "\n".join(f"- {item}" for item in items)


def _format_services(analysis: PRAnalysis) -> str:
    if not analysis.services:
        return "None"
    return ", ".join(
        f"{s.basename} ({'new' if s.is_new else 'modified'}, {s.lines_changed} lines)"
        for s in analysis.services
    )


def _format_api_routes(analysis: PRAnalysis) -> str:
    if not analysis.api_routes:
        return "None"
    return ", ".join(
        f"{r.endpoint} ({', '.join(r.methods)})" for r in analysis.api_routes
    )


def _format_ui_changes(analysis: PRAnalysis) -> str:
    if not analysis.ui_changes:
        return "None"
    return ", ".join(
        f"{u.path} ({'new' if u.is_new else 'modified'} {u.type})"
        for u in analysis.ui_changes
    )


def _format_migrations(analysis: PRAnalysis) -> str:
    if not analysis.migrations:
        return "None"
    parts: list[str] = []
    for m in analysis.migrations:
        ops = ", ".join(f"{op.type} on {op.table}" for op in m.operations)
        destructive = [op for op in m.operations if op.destructive]
        line = f"- {m.name}: {ops} (risk: {m.risk_level}, rollback: {m.rollback_complexity})"
        if destructive:
            line += f" [DESTRUCTIVE: {', '.join(op.type for op in destructive)}]"
        if m.warnings:
            line += f"\n  Warnings: {'; '.join(m.warnings)}"
        parts.append(line)
    return "\n".join(parts)


def _format_ci_status(ci_status: dict) -> str:
    if not ci_status or not ci_status.get("checks"):
        return "No CI data available"
    lines: list[str] = []
    for check in ci_status["checks"]:
        status_label = {"success": "PASS", "failure": "FAIL", "pending": "PENDING"}.get(
            check.get("status", ""), "?"
        )
        lines.append(f"- [{status_label}] {check.get('name', 'unknown')}")
    return "\n".join(lines)


def _format_missing_tests(analysis: PRAnalysis) -> str:
    if not analysis.missing_tests:
        return "None"
    return ", ".join(
        f"{t.service_file} ({t.severity})" for t in analysis.missing_tests
    )


def _format_risks(analysis: PRAnalysis) -> str:
    if not analysis.risks:
        return "None"
    return ", ".join(
        f"{r.description} ({r.level})" for r in analysis.risks
    )
