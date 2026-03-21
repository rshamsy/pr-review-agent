"""Tests for pr_review_agent.graph.nodes — individual node functions in isolation.

Each node is tested with fixture state inputs and mocked external dependencies.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.graph.nodes import (
    _extract_mcp_error,
    analyze_pr_node,
    compute_recommendation_node,
    confirm_context_node,
    exit_with_instructions_node,
    fetch_pr_data,
    fetch_specific_page_node,
    format_output_node,
    generate_checklist_node,
    generate_llm_brief_node,
    score_relevance_node,
    search_notion_node,
    summarize_pr_node,
)
from pr_review_agent.models.brief import IntentDelta, ReviewBrief
from pr_review_agent.models.migration import MigrationInfo
from pr_review_agent.models.notion import (
    NotionContext,
    NotionSearchResult,
    RelevanceScore,
)
from pr_review_agent.models.pr import (
    CICheck,
    CIStatus,
    FileChange,
    PRAnalysis,
    PRData,
    ServiceChangeInfo,
)
from pr_review_agent.models.review import MissingTest, ReviewRecommendation, Risk, TestingChecklistItem


# ===========================================================================
# Tests for fetch_pr_data
# ===========================================================================

class TestFetchPrData:
    """Tests for the fetch_pr_data node."""

    @patch("pr_review_agent.graph.nodes.fetch_ci_checks")
    @patch("pr_review_agent.graph.nodes.fetch_diff")
    @patch("pr_review_agent.graph.nodes.fetch_pr")
    def test_fetches_pr_and_diff(self, mock_fetch_pr, mock_fetch_diff, mock_fetch_ci):
        """fetch_pr_data calls fetch_pr and fetch_diff with the PR number."""
        pr_data = PRData(
            number=39,
            title="Test PR",
            author="dev",
            additions=100,
            deletions=10,
            branch="feature/x",
            files=[FileChange(filename="test.ts", status="added", additions=100)],
        )
        mock_fetch_pr.return_value = pr_data
        mock_fetch_diff.return_value = "diff +100 -10"
        mock_fetch_ci.return_value = CIStatus(
            all_passed=True,
            checks=[CICheck(name="build", status="success", conclusion="SUCCESS")],
        )

        state = {"pr_number": 39}
        result = fetch_pr_data(state)

        mock_fetch_pr.assert_called_once_with(39)
        mock_fetch_diff.assert_called_once_with(39)
        assert result["pr_data"] is pr_data
        assert result["diff_text"] == "diff +100 -10"
        assert result["status"] == "running"

    @patch("pr_review_agent.graph.nodes.fetch_ci_checks")
    @patch("pr_review_agent.graph.nodes.fetch_diff")
    @patch("pr_review_agent.graph.nodes.fetch_pr")
    def test_ci_status_included(self, mock_fetch_pr, mock_fetch_diff, mock_fetch_ci):
        """CI status is included in the result when available."""
        mock_fetch_pr.return_value = PRData(number=1, title="T", author="a")
        mock_fetch_diff.return_value = ""
        mock_fetch_ci.return_value = CIStatus(
            all_passed=True,
            checks=[CICheck(name="lint", status="success", conclusion="SUCCESS")],
        )

        result = fetch_pr_data({"pr_number": 1})

        assert result["ci_status"]["all_passed"] is True
        assert len(result["ci_status"]["checks"]) == 1

    @patch("pr_review_agent.graph.nodes.fetch_ci_checks")
    @patch("pr_review_agent.graph.nodes.fetch_diff")
    @patch("pr_review_agent.graph.nodes.fetch_pr")
    def test_ci_failure_handled_gracefully(self, mock_fetch_pr, mock_fetch_diff, mock_fetch_ci):
        """When CI check retrieval fails, an empty dict is returned for ci_status."""
        mock_fetch_pr.return_value = PRData(number=1, title="T", author="a")
        mock_fetch_diff.return_value = ""
        mock_fetch_ci.side_effect = Exception("CI not available")

        result = fetch_pr_data({"pr_number": 1})

        assert result["ci_status"] == {}

    @patch("pr_review_agent.graph.nodes.fetch_repo_test_files")
    @patch("pr_review_agent.graph.nodes.fetch_ci_checks")
    @patch("pr_review_agent.graph.nodes.fetch_diff")
    @patch("pr_review_agent.graph.nodes.fetch_pr")
    def test_populates_repo_test_files(self, mock_fetch_pr, mock_fetch_diff, mock_fetch_ci, mock_fetch_tests):
        """fetch_pr_data populates repo_test_files in the result."""
        mock_fetch_pr.return_value = PRData(number=1, title="T", author="a")
        mock_fetch_diff.return_value = ""
        mock_fetch_ci.return_value = CIStatus(all_passed=True, checks=[])
        mock_fetch_tests.return_value = ["tests/api/payment.test.ts", "tests/lib/auth.test.ts"]

        result = fetch_pr_data({"pr_number": 1})

        assert result["repo_test_files"] == ["tests/api/payment.test.ts", "tests/lib/auth.test.ts"]

    @patch("pr_review_agent.graph.nodes.fetch_repo_test_files")
    @patch("pr_review_agent.graph.nodes.fetch_ci_checks")
    @patch("pr_review_agent.graph.nodes.fetch_diff")
    @patch("pr_review_agent.graph.nodes.fetch_pr")
    def test_repo_test_files_failure_handled_gracefully(self, mock_fetch_pr, mock_fetch_diff, mock_fetch_ci, mock_fetch_tests):
        """When repo test file retrieval fails, empty list is returned."""
        mock_fetch_pr.return_value = PRData(number=1, title="T", author="a")
        mock_fetch_diff.return_value = ""
        mock_fetch_ci.return_value = CIStatus(all_passed=True, checks=[])
        mock_fetch_tests.side_effect = RuntimeError("gh command failed")

        result = fetch_pr_data({"pr_number": 1})

        assert result["repo_test_files"] == []


# ===========================================================================
# Tests for summarize_pr_node
# ===========================================================================

class TestSummarizePrNode:
    """Tests for the summarize_pr_node."""

    @patch("pr_review_agent.graph.nodes.summarize_pr")
    def test_returns_pr_summary(self, mock_summarize):
        """summarize_pr_node calls summarize_pr and returns the summary."""
        mock_summarize.return_value = "This PR adds payment tracking."

        state = {
            "pr_data": PRData(number=1, title="T", author="a"),
            "diff_text": "some diff",
            "model": "claude-sonnet-4-20250514",
        }
        result = summarize_pr_node(state)

        assert result["pr_summary"] == "This PR adds payment tracking."
        mock_summarize.assert_called_once()

    @patch("pr_review_agent.graph.nodes.summarize_pr")
    def test_uses_model_from_state(self, mock_summarize):
        """The model parameter from state is passed to summarize_pr."""
        mock_summarize.return_value = "Summary"

        state = {
            "pr_data": PRData(number=1, title="T", author="a"),
            "diff_text": "diff",
            "model": "claude-opus-4-20250514",
        }
        summarize_pr_node(state)

        call_kwargs = mock_summarize.call_args
        assert call_kwargs[1]["model"] == "claude-opus-4-20250514"

    @patch("pr_review_agent.graph.nodes.summarize_pr")
    def test_defaults_model_when_not_in_state(self, mock_summarize):
        """When model is not in state, defaults to claude-sonnet-4-20250514."""
        mock_summarize.return_value = "Summary"

        state = {
            "pr_data": PRData(number=1, title="T", author="a"),
            "diff_text": "diff",
        }
        summarize_pr_node(state)

        call_kwargs = mock_summarize.call_args
        assert call_kwargs[1]["model"] == "claude-sonnet-4-20250514"


# ===========================================================================
# Tests for analyze_pr_node
# ===========================================================================

class TestAnalyzePrNode:
    """Tests for the analyze_pr_node."""

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.detect_migrations")
    @patch("pr_review_agent.graph.nodes.analyze_pr")
    def test_returns_analysis(self, mock_analyze, mock_detect_migrations, mock_config):
        """analyze_pr_node runs analysis and returns the result."""
        mock_config.return_value = MagicMock(
            test_verification_mode="default",
            test_verification_model="claude-haiku-4-5-20251001",
        )
        pr_data = PRData(
            number=1,
            title="Test",
            author="dev",
            files=[FileChange(filename="test.ts", status="added", additions=50)],
        )
        analysis = PRAnalysis(
            classification="minor",
            total_additions=50,
            total_deletions=0,
        )
        mock_analyze.return_value = analysis
        mock_detect_migrations.return_value = []

        state = {"pr_data": pr_data}
        result = analyze_pr_node(state)

        assert result["pr_analysis"] is analysis
        mock_analyze.assert_called_once()
        call_kwargs = mock_analyze.call_args
        assert call_kwargs[0][0] is pr_data
        assert call_kwargs[1]["verification_mode"] == "default"

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.detect_migrations")
    @patch("pr_review_agent.graph.nodes.analyze_pr")
    def test_migrations_added_to_analysis(self, mock_analyze, mock_detect_migrations, mock_config):
        """Detected migrations are added to the analysis object."""
        mock_config.return_value = MagicMock(
            test_verification_mode="default",
            test_verification_model="claude-haiku-4-5-20251001",
        )
        pr_data = PRData(number=1, title="T", author="a", files=[])
        analysis = PRAnalysis(classification="minor")
        mock_analyze.return_value = analysis

        mock_migrations = [
            MigrationInfo(path="migrations/001.sql", name="001", risk_level="low"),
        ]
        mock_detect_migrations.return_value = mock_migrations

        result = analyze_pr_node({"pr_data": pr_data})

        assert result["pr_analysis"].migrations == mock_migrations

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.detect_migrations")
    @patch("pr_review_agent.graph.nodes.analyze_pr")
    def test_passes_config_options(self, mock_analyze, mock_detect_migrations, mock_config):
        """analyze_pr_node passes verification config to analyze_pr."""
        mock_config.return_value = MagicMock(
            test_verification_mode="advanced",
            test_verification_model="claude-sonnet-4-20250514",
        )
        pr_data = PRData(number=1, title="T", author="a", files=[])
        analysis = PRAnalysis(classification="minor")
        mock_analyze.return_value = analysis
        mock_detect_migrations.return_value = []

        state = {"pr_data": pr_data, "repo_test_files": ["tests/foo.test.ts"]}
        analyze_pr_node(state)

        call_kwargs = mock_analyze.call_args[1]
        assert call_kwargs["verification_mode"] == "advanced"
        assert call_kwargs["verification_model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["repo_test_files"] == ["tests/foo.test.ts"]

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.detect_migrations")
    @patch("pr_review_agent.graph.nodes.analyze_pr")
    def test_repo_test_files_none_when_empty(self, mock_analyze, mock_detect_migrations, mock_config):
        """When repo_test_files is empty list, passes None to analyze_pr."""
        mock_config.return_value = MagicMock(
            test_verification_mode="default",
            test_verification_model="claude-haiku-4-5-20251001",
        )
        pr_data = PRData(number=1, title="T", author="a", files=[])
        analysis = PRAnalysis(classification="minor")
        mock_analyze.return_value = analysis
        mock_detect_migrations.return_value = []

        state = {"pr_data": pr_data, "repo_test_files": []}
        analyze_pr_node(state)

        call_kwargs = mock_analyze.call_args[1]
        assert call_kwargs["repo_test_files"] is None


# ===========================================================================
# Tests for compute_recommendation_node
# ===========================================================================

class TestComputeRecommendationNode:
    """Tests for the compute_recommendation_node."""

    def test_approve_when_no_blockers(self):
        """When LLM recommends approve and no blockers, verdict is 'approve'."""
        brief = ReviewBrief(
            summary="Good PR",
            llm_recommendation="approve",
            llm_confidence=0.9,
            deltas=[],
            key_concerns=[],
        )
        analysis = PRAnalysis(
            classification="minor",
            missing_tests=[],
            migrations=[],
            risks=[],
        )

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert result["recommendation"].verdict == "approve"
        assert result["should_block"] is False

    def test_request_changes_with_critical_missing_tests(self):
        """Critical missing tests create blockers and verdict='request_changes'."""
        brief = ReviewBrief(
            summary="PR ok",
            llm_recommendation="approve",
            llm_confidence=0.8,
        )
        analysis = PRAnalysis(
            classification="major",
            missing_tests=[
                MissingTest(
                    service_file="payment-service.ts",
                    reason="critical_logic_no_test",
                    severity="critical",
                    suggested_test_file="tests/payment-service.test.ts",
                ),
            ],
        )

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert result["recommendation"].verdict == "request_changes"
        assert result["should_block"] is True
        assert len(result["recommendation"].blockers) >= 1
        assert "payment-service.ts" in result["recommendation"].blockers[0]

    def test_request_changes_with_high_risk_migrations(self):
        """High-risk migrations create blockers."""
        brief = ReviewBrief(
            summary="PR with migration",
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        analysis = PRAnalysis(
            classification="major",
            migrations=[
                MigrationInfo(
                    path="migrations/001.sql",
                    name="001",
                    risk_level="high",
                ),
            ],
        )

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert result["recommendation"].verdict == "request_changes"
        assert result["should_block"] is True
        assert any("migration" in b.lower() for b in result["recommendation"].blockers)

    def test_request_changes_with_missing_deltas(self):
        """Missing requirement deltas create blockers."""
        brief = ReviewBrief(
            summary="Incomplete PR",
            llm_recommendation="needs_discussion",
            llm_confidence=0.6,
            deltas=[
                IntentDelta(
                    aspect="Auth",
                    intended="Add authentication",
                    implemented="Not found",
                    status="missing",
                ),
            ],
        )
        analysis = PRAnalysis(classification="major")

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert result["recommendation"].verdict == "request_changes"
        assert any("Auth" in b for b in result["recommendation"].blockers)

    def test_needs_discussion_when_llm_recommends_it(self):
        """When LLM recommends needs_discussion and no explicit blockers."""
        brief = ReviewBrief(
            summary="Unclear PR",
            llm_recommendation="needs_discussion",
            llm_confidence=0.5,
        )
        analysis = PRAnalysis(classification="minor")

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert result["recommendation"].verdict == "needs_discussion"

    def test_llm_request_changes_overrides_approve(self):
        """When LLM recommends request_changes and no required items, verdict matches."""
        brief = ReviewBrief(
            summary="Bad PR",
            llm_recommendation="request_changes",
            llm_confidence=0.7,
            key_concerns=["Security issue"],
        )
        analysis = PRAnalysis(classification="minor")

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert result["recommendation"].verdict == "request_changes"

    def test_required_items_from_missing_tests(self):
        """High-severity missing tests generate 'required' items."""
        brief = ReviewBrief(
            summary="PR",
            llm_recommendation="approve",
            llm_confidence=0.8,
        )
        analysis = PRAnalysis(
            classification="minor",
            missing_tests=[
                MissingTest(
                    service_file="svc.ts",
                    reason="new_service_no_test",
                    severity="high",
                    suggested_test_file="tests/svc.test.ts",
                ),
            ],
        )

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert any("svc.ts" in r for r in result["recommendation"].required)

    def test_suggestions_from_key_concerns(self):
        """Key concerns from the brief become suggestions."""
        brief = ReviewBrief(
            summary="PR",
            llm_recommendation="approve",
            llm_confidence=0.8,
            key_concerns=["Consider edge cases", "Add logging"],
        )
        analysis = PRAnalysis(classification="trivial")

        state = {"review_brief": brief, "pr_analysis": analysis}
        result = compute_recommendation_node(state)

        assert "Consider edge cases" in result["recommendation"].suggestions
        assert "Add logging" in result["recommendation"].suggestions


# ===========================================================================
# Tests for format_output_node
# ===========================================================================

class TestFormatOutputNode:
    """Tests for the format_output_node."""

    @patch("pr_review_agent.graph.nodes.format_review_markdown")
    @patch("pr_review_agent.graph.nodes.display_results")
    def test_returns_markdown_and_status(self, mock_display, mock_format):
        """format_output_node returns markdown comment and status='complete'."""
        mock_format.return_value = "# Review\nAll good."

        state = {
            "pr_number": 42,
            "verbose": False,
            "post_comment": False,
            "review_brief": ReviewBrief(summary="Good"),
            "recommendation": ReviewRecommendation(verdict="approve"),
            "pr_analysis": PRAnalysis(classification="trivial"),
            "pr_data": PRData(number=42, title="T", author="a"),
        }
        result = format_output_node(state)

        assert result["markdown_comment"] == "# Review\nAll good."
        assert result["status"] == "complete"
        mock_display.assert_called_once()

    @patch("pr_review_agent.graph.nodes.post_pr_comment")
    @patch("pr_review_agent.graph.nodes.format_review_markdown")
    @patch("pr_review_agent.graph.nodes.display_results")
    def test_posts_comment_when_requested(self, mock_display, mock_format, mock_post):
        """When post_comment is True, the review is posted to GitHub."""
        mock_format.return_value = "# Review"

        state = {
            "pr_number": 42,
            "verbose": False,
            "post_comment": True,
            "review_brief": ReviewBrief(summary="Good"),
            "recommendation": ReviewRecommendation(verdict="approve"),
            "pr_analysis": PRAnalysis(classification="trivial"),
            "pr_data": PRData(number=42, title="T", author="a"),
        }
        format_output_node(state)

        mock_post.assert_called_once_with(42, "# Review")

    @patch("pr_review_agent.graph.nodes.post_pr_comment")
    @patch("pr_review_agent.graph.nodes.format_review_markdown")
    @patch("pr_review_agent.graph.nodes.display_results")
    def test_comment_post_failure_handled(self, mock_display, mock_format, mock_post):
        """When posting to GitHub fails, the error is handled gracefully."""
        mock_format.return_value = "# Review"
        mock_post.side_effect = RuntimeError("GitHub API error")

        state = {
            "pr_number": 42,
            "verbose": False,
            "post_comment": True,
            "review_brief": ReviewBrief(summary="Good"),
            "recommendation": ReviewRecommendation(verdict="approve"),
            "pr_analysis": PRAnalysis(classification="trivial"),
            "pr_data": PRData(number=42, title="T", author="a"),
        }
        # Should not raise
        result = format_output_node(state)

        assert result["status"] == "complete"

    @patch("pr_review_agent.graph.nodes.format_review_markdown")
    @patch("pr_review_agent.graph.nodes.display_results")
    def test_no_post_when_not_requested(self, mock_display, mock_format):
        """When post_comment is False, no GitHub comment is posted."""
        mock_format.return_value = "# Review"

        state = {
            "pr_number": 42,
            "verbose": False,
            "post_comment": False,
            "review_brief": ReviewBrief(summary="Good"),
            "recommendation": ReviewRecommendation(verdict="approve"),
            "pr_analysis": PRAnalysis(classification="trivial"),
            "pr_data": PRData(number=42, title="T", author="a"),
        }
        format_output_node(state)

        # post_pr_comment should not have been called at all


# ===========================================================================
# Tests for score_relevance_node
# ===========================================================================

class TestScoreRelevanceNode:
    """Tests for the score_relevance_node."""

    @patch("pr_review_agent.graph.nodes.score_relevance")
    def test_scores_each_notion_result(self, mock_score):
        """score_relevance is called for each Notion search result."""
        results = [
            NotionSearchResult(page_id="p1", title="Page 1", url="url1", content="c1"),
            NotionSearchResult(page_id="p2", title="Page 2", url="url2", content="c2"),
        ]
        mock_score.side_effect = [
            RelevanceScore(
                page_id="p1", title="Page 1", score=8.0, explanation="good",
            ),
            RelevanceScore(
                page_id="p2", title="Page 2", score=3.0, explanation="poor",
            ),
        ]

        state = {
            "pr_summary": "PR summary text",
            "notion_results": results,
        }
        result = score_relevance_node(state)

        assert len(result["relevance_scores"]) == 2
        # Results should be sorted by score descending
        assert result["relevance_scores"][0].score == 8.0
        assert result["relevance_scores"][1].score == 3.0

    @patch("pr_review_agent.graph.nodes.score_relevance")
    def test_empty_notion_results(self, mock_score):
        """With no Notion results, an empty list is returned."""
        state = {"pr_summary": "test", "notion_results": []}
        result = score_relevance_node(state)

        assert result["relevance_scores"] == []
        mock_score.assert_not_called()

    @patch("pr_review_agent.graph.nodes.score_relevance")
    def test_scores_sorted_descending(self, mock_score):
        """Results are sorted by score in descending order."""
        results = [
            NotionSearchResult(page_id="p1", title="Low", content="c"),
            NotionSearchResult(page_id="p2", title="High", content="c"),
        ]
        mock_score.side_effect = [
            RelevanceScore(page_id="p1", title="Low", score=2.0),
            RelevanceScore(page_id="p2", title="High", score=9.0),
        ]

        state = {"pr_summary": "test", "notion_results": results}
        result = score_relevance_node(state)

        assert result["relevance_scores"][0].title == "High"
        assert result["relevance_scores"][1].title == "Low"


# ===========================================================================
# Tests for confirm_context_node
# ===========================================================================

class TestConfirmContextNode:
    """Tests for the confirm_context_node."""

    @patch("pr_review_agent.graph.nodes.confirm_context")
    def test_returns_user_choice_with_contexts(self, mock_confirm):
        """confirm_context_node wraps confirm_context and merges with supplementary."""
        context = NotionContext(
            page_id="p1", title="T", description="D", raw_content="C",
        )
        mock_confirm.return_value = ("confirmed", [context], None)

        state = {
            "relevance_scores": [
                RelevanceScore(page_id="p1", title="T", score=8.0),
            ],
            "supplementary_contexts": [],
        }
        result = confirm_context_node(state)

        assert result["user_confirmation"] == "confirmed"
        assert len(result["notion_contexts"]) == 1
        assert result["notion_contexts"][0] is context
        assert result["user_provided_url"] is None

    @patch("pr_review_agent.graph.nodes.confirm_context")
    def test_exit_path(self, mock_confirm):
        """When user exits, confirmation is 'exit' and contexts is empty."""
        mock_confirm.return_value = ("exit", [], None)

        state = {"relevance_scores": [], "supplementary_contexts": []}
        result = confirm_context_node(state)

        assert result["user_confirmation"] == "exit"
        assert result["notion_contexts"] == []

    @patch("pr_review_agent.graph.nodes.confirm_context")
    def test_merges_supplementary_contexts(self, mock_confirm):
        """User-selected contexts are merged with supplementary contexts."""
        user_ctx = NotionContext(
            page_id="p1", title="User Page", description="D", raw_content="C",
        )
        supp_ctx = NotionContext(
            page_id="p2", title="Standup Notes", description="Supplementary", raw_content="Notes",
        )
        mock_confirm.return_value = ("confirmed", [user_ctx], None)

        state = {
            "relevance_scores": [],
            "supplementary_contexts": [supp_ctx],
        }
        result = confirm_context_node(state)

        assert result["user_confirmation"] == "confirmed"
        assert len(result["notion_contexts"]) == 2
        assert result["notion_contexts"][0] is user_ctx
        assert result["notion_contexts"][1] is supp_ctx


# ===========================================================================
# Tests for exit_with_instructions_node
# ===========================================================================

class TestExitWithInstructionsNode:
    """Tests for the exit_with_instructions_node."""

    @patch("pr_review_agent.graph.nodes.display_exit_instructions")
    def test_returns_blocked_status(self, mock_display):
        """exit_with_instructions_node returns blocked status."""
        result = exit_with_instructions_node({})

        assert result["should_block"] is True
        assert result["status"] == "blocked"
        mock_display.assert_called_once()


# ===========================================================================
# Tests for generate_llm_brief_node
# ===========================================================================

class TestGenerateLlmBriefNode:
    """Tests for the generate_llm_brief_node."""

    @patch("pr_review_agent.graph.nodes.generate_brief")
    def test_returns_review_brief(self, mock_generate):
        """generate_llm_brief_node calls generate_brief and returns the result."""
        brief = ReviewBrief(
            summary="Good PR",
            llm_recommendation="approve",
            llm_confidence=0.85,
        )
        mock_generate.return_value = brief

        notion_ctx = NotionContext(
            page_id="p1", title="Feature", raw_content="content",
        )
        state = {
            "notion_contexts": [notion_ctx],
            "pr_data": PRData(number=1, title="T", author="a"),
            "pr_analysis": PRAnalysis(classification="minor"),
            "diff_text": "diff content",
            "model": "claude-sonnet-4-20250514",
        }
        result = generate_llm_brief_node(state)

        assert result["review_brief"] is brief
        mock_generate.assert_called_once_with(
            notion_contexts=[notion_ctx],
            pr_data=state["pr_data"],
            analysis=state["pr_analysis"],
            diff_text="diff content",
            ci_status=None,
            model="claude-sonnet-4-20250514",
        )


# ===========================================================================
# Tests for _extract_mcp_error
# ===========================================================================

class TestExtractMcpError:
    """Tests for the _extract_mcp_error helper."""

    def test_plain_exception(self):
        """A plain exception returns its string representation."""
        exc = RuntimeError("connection refused")
        assert _extract_mcp_error(exc) == "connection refused"

    def test_exception_group_unwraps_first(self):
        """An ExceptionGroup is unwrapped to the first sub-exception."""
        inner = RuntimeError("server crashed")
        group = ExceptionGroup("TaskGroup", [inner])
        assert _extract_mcp_error(group) == "server crashed"

    def test_nested_exception_group(self):
        """Nested ExceptionGroups are recursively unwrapped."""
        inner = ValueError("bad auth token")
        inner_group = ExceptionGroup("inner", [inner])
        outer_group = ExceptionGroup("outer", [inner_group])
        assert _extract_mcp_error(outer_group) == "bad auth token"

    def test_exception_group_multiple_takes_first(self):
        """With multiple sub-exceptions, the first one is returned."""
        exc1 = RuntimeError("first error")
        exc2 = ValueError("second error")
        group = ExceptionGroup("multi", [exc1, exc2])
        assert _extract_mcp_error(group) == "first error"


# ===========================================================================
# Tests for search_notion_node error handling
# ===========================================================================

class TestSearchNotionNodeErrorHandling:
    """Tests for search_notion_node MCP error handling."""

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.asyncio.run")
    def test_exception_group_returns_empty_results(self, mock_run, mock_config):
        """When asyncio.run raises ExceptionGroup, returns empty results with error."""
        mock_config.return_value = MagicMock(notion_api_key="test-key", get_context_page_urls=MagicMock(return_value=[]))
        inner = RuntimeError("server process exited")
        mock_run.side_effect = ExceptionGroup("TaskGroup", [inner])

        state = {"pr_summary": "Test PR summary"}
        result = search_notion_node(state)

        assert result["notion_results"] == []
        assert result["supplementary_contexts"] == []
        assert "server process exited" in result["error"]

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.asyncio.run")
    def test_runtime_error_returns_empty_results(self, mock_run, mock_config):
        """When asyncio.run raises RuntimeError, returns empty results with error."""
        mock_config.return_value = MagicMock(notion_api_key="test-key", get_context_page_urls=MagicMock(return_value=[]))
        mock_run.side_effect = RuntimeError("NOTION_API_KEY is not set")

        state = {"pr_summary": "Test PR summary"}
        result = search_notion_node(state)

        assert result["notion_results"] == []
        assert result["supplementary_contexts"] == []
        assert "NOTION_API_KEY is not set" in result["error"]

    @patch("pr_review_agent.graph.nodes.contextual_search")
    @patch("pr_review_agent.graph.nodes.NotionMCPClient")
    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.asyncio.run")
    def test_success_returns_results(self, mock_run, mock_config, mock_client_cls, mock_search):
        """On success, returns notion_results with no error."""
        mock_config.return_value = MagicMock(notion_api_key="test-key", get_context_page_urls=MagicMock(return_value=[]))
        mock_run.return_value = ([MagicMock()], [])

        state = {"pr_summary": "Test PR summary"}
        result = search_notion_node(state)

        assert len(result["notion_results"]) == 1
        assert result["supplementary_contexts"] == []
        assert "error" not in result

    @patch("pr_review_agent.graph.nodes.contextual_search")
    @patch("pr_review_agent.graph.nodes.NotionMCPClient")
    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.asyncio.run")
    def test_supplementary_contexts_returned(self, mock_run, mock_config, mock_client_cls, mock_search):
        """When context page URLs are configured, supplementary contexts are fetched."""
        supp_ctx = NotionContext(
            page_id="supp-1", title="Standup", description="Supplementary", raw_content="Notes",
        )
        mock_config.return_value = MagicMock(
            notion_api_key="test-key",
            get_context_page_urls=MagicMock(return_value=["https://notion.so/standup"]),
        )
        mock_run.return_value = ([MagicMock()], [supp_ctx])

        state = {"pr_summary": "Test PR summary"}
        result = search_notion_node(state)

        assert len(result["supplementary_contexts"]) == 1
        assert result["supplementary_contexts"][0] is supp_ctx


# ===========================================================================
# Tests for fetch_specific_page_node error handling
# ===========================================================================

class TestFetchSpecificPageNodeErrorHandling:
    """Tests for fetch_specific_page_node MCP error handling."""

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.asyncio.run")
    def test_exception_group_returns_empty_scores(self, mock_run, mock_config):
        """When asyncio.run raises ExceptionGroup, returns empty scores with error."""
        mock_config.return_value = MagicMock(notion_api_key="test-key")
        inner = RuntimeError("npx failed")
        mock_run.side_effect = ExceptionGroup("TaskGroup", [inner])

        state = {
            "user_provided_url": "https://notion.so/page-123",
            "pr_summary": "Test PR summary",
        }
        result = fetch_specific_page_node(state)

        assert result["relevance_scores"] == []
        assert "Notion connection failed" in result["error"]
        assert "npx failed" in result["error"]

    @patch("pr_review_agent.config.get_config")
    @patch("pr_review_agent.graph.nodes.asyncio.run")
    def test_runtime_error_returns_empty_scores(self, mock_run, mock_config):
        """When asyncio.run raises RuntimeError, returns empty scores with error."""
        mock_config.return_value = MagicMock(notion_api_key="test-key")
        mock_run.side_effect = RuntimeError("NOTION_API_KEY is not set")

        state = {
            "user_provided_url": "https://notion.so/page-123",
            "pr_summary": "Test PR",
        }
        result = fetch_specific_page_node(state)

        assert result["relevance_scores"] == []
        assert "NOTION_API_KEY is not set" in result["error"]


# ===========================================================================
# Tests for generate_checklist_node
# ===========================================================================

class TestGenerateChecklistNode:
    """Tests for generate_checklist_node."""

    @patch("pr_review_agent.graph.nodes.generate_testing_checklist")
    def test_returns_checklist(self, mock_gen):
        """generate_checklist_node calls generate_testing_checklist and returns result."""
        items = [
            TestingChecklistItem(
                category="pre-flight",
                description="Verify deployment",
                priority="must",
            ),
        ]
        mock_gen.return_value = items

        state = {
            "pr_number": 42,
            "pr_analysis": PRAnalysis(classification="minor"),
        }
        result = generate_checklist_node(state)

        assert result["testing_checklist"] is items
        mock_gen.assert_called_once_with(42, state["pr_analysis"])

    @patch("pr_review_agent.graph.nodes.generate_testing_checklist")
    def test_empty_checklist(self, mock_gen):
        """When no checklist items are generated, returns empty list."""
        mock_gen.return_value = []

        state = {
            "pr_number": 1,
            "pr_analysis": PRAnalysis(classification="trivial"),
        }
        result = generate_checklist_node(state)

        assert result["testing_checklist"] == []


# ===========================================================================
# Tests for generate_llm_brief_node with CI status
# ===========================================================================

class TestGenerateLlmBriefNodeCiStatus:
    """Tests for ci_status being passed to generate_brief."""

    @patch("pr_review_agent.graph.nodes.generate_brief")
    def test_ci_status_passed(self, mock_generate):
        """CI status from state is forwarded to generate_brief."""
        brief = ReviewBrief(
            summary="Brief",
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        mock_generate.return_value = brief

        ci = {"all_passed": True, "checks": [{"name": "lint", "status": "success"}]}
        state = {
            "notion_contexts": [],
            "pr_data": PRData(number=1, title="T", author="a"),
            "pr_analysis": PRAnalysis(classification="minor"),
            "diff_text": "diff",
            "ci_status": ci,
        }
        result = generate_llm_brief_node(state)

        assert result["review_brief"] is brief
        mock_generate.assert_called_once_with(
            notion_contexts=[],
            pr_data=state["pr_data"],
            analysis=state["pr_analysis"],
            diff_text="diff",
            ci_status=ci,
            model="claude-sonnet-4-20250514",
        )
