"""Tests for PR review output formatting — markdown and terminal."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from rich.console import Console

from pr_review_agent.models.brief import IntentDelta, ReviewBrief
from pr_review_agent.models.migration import MigrationInfo, MigrationOperation
from pr_review_agent.models.notion import NotionContext
from pr_review_agent.models.pr import PRAnalysis, PRData
from pr_review_agent.models.review import MissingTest, ReviewRecommendation, TestingChecklistItem
from pr_review_agent.output.markdown import format_review_markdown
from pr_review_agent.output.terminal import display_results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_state(
    pr_data: PRData | None = None,
    notion_contexts: list[NotionContext] | None = None,
    analysis: PRAnalysis | None = None,
    brief: ReviewBrief | None = None,
    recommendation: ReviewRecommendation | None = None,
) -> dict[str, Any]:
    """Build a state dict matching AgentState shape."""
    state: dict[str, Any] = {}
    if pr_data is not None:
        state["pr_data"] = pr_data
    if notion_contexts is not None:
        state["notion_contexts"] = notion_contexts
    if analysis is not None:
        state["pr_analysis"] = analysis
    if brief is not None:
        state["review_brief"] = brief
    if recommendation is not None:
        state["recommendation"] = recommendation
    return state


# ===========================================================================
# format_review_markdown tests
# ===========================================================================


class TestFormatReviewMarkdown:
    """Tests for the markdown output formatter."""

    def test_full_state_contains_header(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        # Header should contain verdict in uppercase
        assert "# " in md
        assert "REQUEST CHANGES" in md

    def test_full_state_contains_summary(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## Summary" in md
        assert sample_brief.summary in md

    def test_full_state_contains_notion_intent_section(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## Feature Intent (from Notion)" in md
        assert sample_notion_context.title in md
        assert sample_notion_context.description in md
        assert sample_notion_context.page_url in md

    def test_full_state_contains_what_was_requested(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## What Was Requested" in md
        for item in sample_brief.what_was_requested:
            assert item in md

    def test_full_state_contains_what_was_implemented(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## What Was Implemented" in md
        for item in sample_brief.what_was_implemented:
            assert item in md

    def test_full_state_contains_deltas_table(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## Intent vs Implementation" in md
        assert "| Aspect | Intended | Implemented | Status |" in md
        # Check each delta row appears
        for delta in sample_brief.deltas:
            assert delta.aspect in md
            assert delta.intended in md
            assert delta.implemented in md

    def test_full_state_contains_code_analysis(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## Code Analysis" in md
        assert "major" in md
        assert "+682/-35" in md
        assert "Services:" in md
        assert "API Routes:" in md
        assert "Risks:" in md

    def test_full_state_contains_recommendation(
        self,
        sample_pr_data: PRData,
        sample_notion_context: NotionContext,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            pr_data=sample_pr_data,
            notion_contexts=[sample_notion_context],
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## Recommendation" in md
        assert "REQUEST CHANGES" in md
        assert "80%" in md
        # Blockers section
        assert "### Blockers" in md
        for b in sample_recommendation.blockers:
            assert b in md
        # Required changes section
        assert "### Required Changes" in md
        for r in sample_recommendation.required:
            assert r in md
        # Suggestions section
        assert "### Suggestions" in md
        for s in sample_recommendation.suggestions:
            assert s in md

    def test_full_state_contains_positive_findings(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(brief=sample_brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## Positive Findings" in md
        for finding in sample_brief.positive_findings:
            assert finding in md

    def test_full_state_contains_key_concerns(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(brief=sample_brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## Key Concerns" in md
        for concern in sample_brief.key_concerns:
            assert concern in md

    def test_full_state_contains_footer(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(brief=sample_brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "---" in md
        assert "PR Review Agent" in md

    # -------------------------------------------------------------------
    # Missing/empty fields
    # -------------------------------------------------------------------

    def test_empty_state_returns_fallback(self) -> None:
        md = format_review_markdown({})
        assert "No review results available" in md

    def test_missing_brief_returns_fallback(
        self,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "No review results available" in md

    def test_missing_recommendation_returns_fallback(
        self,
        sample_brief: ReviewBrief,
    ) -> None:
        state = _build_state(brief=sample_brief)
        md = format_review_markdown(state)
        assert "No review results available" in md

    def test_no_notion_context_skips_intent_section(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "Feature Intent (from Notion)" not in md

    def test_empty_notion_contexts_skips_intent_section(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            brief=sample_brief,
            recommendation=sample_recommendation,
            notion_contexts=[],
        )
        md = format_review_markdown(state)
        assert "Feature Intent (from Notion)" not in md

    def test_no_analysis_skips_code_analysis_section(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        state = _build_state(
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## Code Analysis" not in md

    def test_empty_deltas_skips_table(
        self,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        brief = ReviewBrief(
            summary="Minimal review.",
            deltas=[],
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        state = _build_state(brief=brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "Intent vs Implementation" not in md

    def test_empty_what_was_requested_skips_section(
        self,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        brief = ReviewBrief(
            summary="Minimal review.",
            what_was_requested=[],
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        state = _build_state(brief=brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## What Was Requested" not in md

    def test_empty_what_was_implemented_skips_section(
        self,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        brief = ReviewBrief(
            summary="Minimal review.",
            what_was_implemented=[],
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        state = _build_state(brief=brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## What Was Implemented" not in md

    def test_empty_positive_findings_skips_section(
        self,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        brief = ReviewBrief(
            summary="Minimal review.",
            positive_findings=[],
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        state = _build_state(brief=brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## Positive Findings" not in md

    def test_empty_key_concerns_skips_section(
        self,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        brief = ReviewBrief(
            summary="Minimal review.",
            key_concerns=[],
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        state = _build_state(brief=brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## Key Concerns" not in md

    def test_no_blockers_skips_blockers_section(
        self,
        sample_brief: ReviewBrief,
    ) -> None:
        rec = ReviewRecommendation(
            verdict="approve",
            blockers=[],
            required=[],
            suggestions=[],
        )
        state = _build_state(brief=sample_brief, recommendation=rec)
        md = format_review_markdown(state)
        assert "### Blockers" not in md

    def test_no_required_changes_skips_section(
        self,
        sample_brief: ReviewBrief,
    ) -> None:
        rec = ReviewRecommendation(
            verdict="approve",
            blockers=[],
            required=[],
            suggestions=["Consider adding tests"],
        )
        state = _build_state(brief=sample_brief, recommendation=rec)
        md = format_review_markdown(state)
        assert "### Required Changes" not in md

    def test_approve_verdict_emoji(
        self,
        sample_brief: ReviewBrief,
    ) -> None:
        rec = ReviewRecommendation(verdict="approve")
        state = _build_state(brief=sample_brief, recommendation=rec)
        md = format_review_markdown(state)
        assert "&#x2705;" in md
        assert "APPROVE" in md

    def test_needs_discussion_verdict_emoji(
        self,
        sample_brief: ReviewBrief,
    ) -> None:
        rec = ReviewRecommendation(verdict="needs_discussion")
        state = _build_state(brief=sample_brief, recommendation=rec)
        md = format_review_markdown(state)
        assert "&#x1F4AC;" in md
        assert "NEEDS DISCUSSION" in md

    def test_notion_context_without_description(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        notion = NotionContext(
            page_id="xyz",
            title="Bare Notion Page",
            description="",
            page_url="",
        )
        state = _build_state(
            brief=sample_brief,
            recommendation=sample_recommendation,
            notion_contexts=[notion],
        )
        md = format_review_markdown(state)
        assert "Bare Notion Page" in md
        # The description line should not produce empty content
        assert "View in Notion" not in md  # empty page_url skipped

    def test_delta_status_badges(
        self,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        brief = ReviewBrief(
            summary="Delta badges test.",
            deltas=[
                IntentDelta(aspect="A", intended="x", implemented="x", status="match"),
                IntentDelta(aspect="B", intended="y", implemented="z", status="partial"),
                IntentDelta(aspect="C", intended="w", implemented="", status="missing"),
                IntentDelta(aspect="D", intended="", implemented="v", status="extra"),
            ],
            llm_recommendation="approve",
            llm_confidence=0.5,
        )
        state = _build_state(brief=brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "MATCH" in md
        assert "PARTIAL" in md
        assert "MISSING" in md
        assert "EXTRA" in md

    def test_multiple_contexts_rendered(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """Multiple notion contexts are all rendered in the Feature Intent section."""
        ctx1 = NotionContext(
            page_id="p1", title="Feature Spec",
            description="Main spec", page_url="https://notion.so/spec",
        )
        ctx2 = NotionContext(
            page_id="p2", title="Standup Notes",
            description="Daily notes", page_url="https://notion.so/standup",
        )
        state = _build_state(
            brief=sample_brief,
            recommendation=sample_recommendation,
            notion_contexts=[ctx1, ctx2],
        )
        md = format_review_markdown(state)
        assert "## Feature Intent (from Notion)" in md
        assert "Feature Spec" in md
        assert "Standup Notes" in md
        assert "https://notion.so/spec" in md
        assert "https://notion.so/standup" in md


# ===========================================================================
# display_results tests
# ===========================================================================


class TestDisplayResults:
    """Tests for the Rich terminal display function."""

    def test_display_results_runs_without_error(
        self,
        sample_pr_data: PRData,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """display_results should not raise with a fully populated state."""
        state = _build_state(
            pr_data=sample_pr_data,
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        # Redirect output to a quiet console so nothing prints to test output
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state)

    def test_display_results_verbose_runs_without_error(
        self,
        sample_pr_data: PRData,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """display_results with verbose=True should not raise."""
        state = _build_state(
            pr_data=sample_pr_data,
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state, verbose=True)

    def test_display_results_empty_state_runs_without_error(self) -> None:
        """display_results should handle empty state gracefully."""
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results({})

    def test_display_results_missing_brief(
        self,
        sample_pr_data: PRData,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """display_results should handle missing brief without crashing."""
        state = _build_state(
            pr_data=sample_pr_data,
            recommendation=sample_recommendation,
        )
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state)

    def test_display_results_no_deltas(
        self,
        sample_pr_data: PRData,
        sample_analysis: PRAnalysis,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """display_results should handle a brief with no deltas."""
        brief = ReviewBrief(
            summary="No deltas here.",
            deltas=[],
            llm_recommendation="approve",
            llm_confidence=1.0,
        )
        state = _build_state(
            pr_data=sample_pr_data,
            analysis=sample_analysis,
            brief=brief,
            recommendation=sample_recommendation,
        )
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state)

    def test_display_results_no_blockers_or_required(
        self,
        sample_pr_data: PRData,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
    ) -> None:
        """display_results should handle recommendation with no blockers/required."""
        rec = ReviewRecommendation(
            verdict="approve",
            blockers=[],
            required=[],
            suggestions=[],
        )
        state = _build_state(
            pr_data=sample_pr_data,
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=rec,
        )
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state)

    def test_display_results_with_ci_status(
        self,
        sample_pr_data: PRData,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """display_results renders CI status section without errors."""
        state = _build_state(
            pr_data=sample_pr_data,
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        state["ci_status"] = {
            "all_passed": False,
            "checks": [
                {"name": "lint", "status": "success"},
                {"name": "tests", "status": "failure"},
            ],
        }
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state)

    def test_display_results_with_checklist(
        self,
        sample_pr_data: PRData,
        sample_analysis: PRAnalysis,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """display_results renders checklist panel without errors."""
        state = _build_state(
            pr_data=sample_pr_data,
            analysis=sample_analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        state["testing_checklist"] = [
            TestingChecklistItem(category="pre-flight", description="Verify deployment", priority="must"),
        ]
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state)

    def test_display_results_with_migrations(
        self,
        sample_pr_data: PRData,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """display_results renders migration details without errors."""
        migration = MigrationInfo(
            path="m.sql", name="add_table", risk_level="medium",
            operations=[MigrationOperation(type="CREATE_TABLE", table="users", details="", destructive=False)],
            warnings=["Check indexes"], rollback_complexity="easy",
        )
        analysis = PRAnalysis(classification="major", migrations=[migration])
        state = _build_state(
            pr_data=sample_pr_data,
            analysis=analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        quiet_console = Console(quiet=True)
        with patch("pr_review_agent.output.terminal.console", quiet_console):
            display_results(state)


# ===========================================================================
# Markdown output — new sections
# ===========================================================================


class TestFormatReviewMarkdownNewSections:
    """Tests for new markdown output sections: CI status, migrations, missing tests, checklist."""

    def test_ci_status_rendered(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """CI status checks appear in markdown."""
        state = _build_state(brief=sample_brief, recommendation=sample_recommendation)
        state["ci_status"] = {
            "checks": [
                {"name": "ESLint", "status": "success"},
                {"name": "Vitest", "status": "failure"},
            ],
        }
        md = format_review_markdown(state)
        assert "## CI/CD Status" in md
        assert "ESLint" in md
        assert "Vitest" in md
        assert "&#x2705;" in md  # success emoji
        assert "&#x274C;" in md  # failure emoji

    def test_no_ci_status_skips_section(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """No CI status data means no CI/CD Status section."""
        state = _build_state(brief=sample_brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## CI/CD Status" not in md

    def test_migration_details_rendered(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """Per-migration breakdown appears in markdown."""
        migration = MigrationInfo(
            path="m.sql", name="add_payments", risk_level="medium",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table="Payment", details="", destructive=False),
            ],
            warnings=["Review indexes"],
            rollback_complexity="easy",
        )
        analysis = PRAnalysis(classification="major", migrations=[migration])
        state = _build_state(
            analysis=analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "**add_payments**" in md
        assert "risk: medium" in md
        assert "rollback: easy" in md
        assert "CREATE_TABLE on `Payment`" in md
        assert "Review indexes" in md

    def test_missing_tests_rendered(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """Missing tests section appears in markdown."""
        analysis = PRAnalysis(
            classification="major",
            missing_tests=[
                MissingTest(
                    service_file="lib/services/pay.ts",
                    reason="new_service_no_test",
                    severity="critical",
                    suggested_test_file="tests/lib/services/pay.test.ts",
                ),
            ],
        )
        state = _build_state(
            analysis=analysis,
            brief=sample_brief,
            recommendation=sample_recommendation,
        )
        md = format_review_markdown(state)
        assert "## Missing Tests" in md
        assert "CRITICAL" in md
        assert "`lib/services/pay.ts`" in md
        assert "`tests/lib/services/pay.test.ts`" in md

    def test_checklist_rendered(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """Browser testing checklist appears in markdown."""
        state = _build_state(brief=sample_brief, recommendation=sample_recommendation)
        state["testing_checklist"] = [
            TestingChecklistItem(category="pre-flight", description="Verify deployment", priority="must"),
            TestingChecklistItem(category="integration", description="Test GET /api/pay", priority="should"),
        ]
        md = format_review_markdown(state)
        assert "## Browser Testing Checklist" in md
        assert "Verify deployment" in md
        assert "Test GET /api/pay" in md

    def test_no_checklist_skips_section(
        self,
        sample_brief: ReviewBrief,
        sample_recommendation: ReviewRecommendation,
    ) -> None:
        """No checklist data means no checklist section."""
        state = _build_state(brief=sample_brief, recommendation=sample_recommendation)
        md = format_review_markdown(state)
        assert "## Browser Testing Checklist" not in md
