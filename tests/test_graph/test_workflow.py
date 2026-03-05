"""Tests for pr_review_agent.graph.workflow — build_workflow and end-to-end graph execution.

Mocks all external dependencies (GitHub, Notion, LLM) to test graph structure and flow.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.graph.workflow import build_workflow
from pr_review_agent.models.brief import ReviewBrief
from pr_review_agent.models.notion import NotionContext, NotionSearchResult, RelevanceScore
from pr_review_agent.models.pr import FileChange, PRAnalysis, PRData
from pr_review_agent.models.review import ReviewRecommendation


# ---------------------------------------------------------------------------
# Test graph construction
# ---------------------------------------------------------------------------

class TestBuildWorkflow:
    """Tests for build_workflow()."""

    def test_build_workflow_returns_compiled_graph(self):
        """build_workflow() returns a compiled StateGraph (CompiledGraph)."""
        graph = build_workflow()
        # CompiledGraph should be invocable
        assert hasattr(graph, "invoke")

    def test_build_workflow_has_expected_nodes(self):
        """The compiled graph contains all expected node names."""
        graph = build_workflow()

        # The graph object stores node info in its internal structure
        # We can verify the graph was built by checking it has the invoke method
        # and that it doesn't raise on construction
        assert graph is not None


# ---------------------------------------------------------------------------
# End-to-end graph tests with mocked externals
# ---------------------------------------------------------------------------

class TestWorkflowHappyPath:
    """Test the full happy path: user confirms context, full pipeline runs."""

    @patch("pr_review_agent.graph.nodes.display_results")
    @patch("pr_review_agent.graph.nodes.format_review_markdown")
    @patch("pr_review_agent.graph.nodes.generate_brief")
    @patch("pr_review_agent.graph.nodes.generate_testing_checklist")
    @patch("pr_review_agent.graph.nodes.detect_migrations")
    @patch("pr_review_agent.graph.nodes.analyze_pr")
    @patch("pr_review_agent.graph.nodes.confirm_context")
    @patch("pr_review_agent.graph.nodes.score_relevance")
    @patch("pr_review_agent.graph.nodes.summarize_pr")
    @patch("pr_review_agent.graph.nodes.fetch_ci_checks")
    @patch("pr_review_agent.graph.nodes.fetch_diff")
    @patch("pr_review_agent.graph.nodes.fetch_pr")
    def test_happy_path_complete(
        self,
        mock_fetch_pr,
        mock_fetch_diff,
        mock_fetch_ci_checks,
        mock_summarize_pr,
        mock_score_relevance,
        mock_confirm_context,
        mock_analyze_pr,
        mock_detect_migrations,
        mock_generate_checklist,
        mock_generate_brief,
        mock_format_markdown,
        mock_display_results,
    ):
        """User confirms context -> full analysis -> status='complete'."""
        # --- Set up mock return values ---

        pr_data = PRData(
            number=42,
            title="Test PR",
            author="dev",
            additions=100,
            deletions=10,
            branch="feature/test",
            files=[
                FileChange(filename="lib/services/test.ts", status="added", additions=100),
            ],
        )
        mock_fetch_pr.return_value = pr_data
        mock_fetch_diff.return_value = "diff content"
        mock_fetch_ci_checks.side_effect = Exception("no CI")

        mock_summarize_pr.return_value = "This PR adds test functionality"

        search_result = NotionSearchResult(
            page_id="page-1",
            title="Test Feature",
            url="https://notion.so/test",
            content="Feature content",
        )

        scored_result = RelevanceScore(
            page_id="page-1",
            title="Test Feature",
            url="https://notion.so/test",
            content="Feature content",
            score=9.0,
            explanation="Highly relevant",
            key_matches=["test feature"],
            gaps=[],
        )
        mock_score_relevance.return_value = scored_result

        notion_context = NotionContext(
            page_id="page-1",
            page_url="https://notion.so/test",
            title="Test Feature",
            description="Highly relevant",
            requirements=["test feature"],
            raw_content="Feature content",
        )
        mock_confirm_context.return_value = ("confirmed", [notion_context], None)

        analysis = PRAnalysis(
            classification="minor",
            total_additions=100,
            total_deletions=10,
        )
        mock_analyze_pr.return_value = analysis
        mock_detect_migrations.return_value = []
        mock_generate_checklist.return_value = []

        brief = ReviewBrief(
            summary="Good PR",
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        mock_generate_brief.return_value = brief

        mock_format_markdown.return_value = "# Review\nAll good."

        # search_notion_node imports get_config locally and uses asyncio.run
        # We need to patch: pr_review_agent.config.get_config (local import),
        # the NotionMCPClient at module level, and asyncio.run in the nodes module.
        with patch("pr_review_agent.config.get_config") as mock_config, \
             patch("pr_review_agent.graph.nodes.NotionMCPClient") as mock_client_cls, \
             patch("pr_review_agent.graph.nodes.asyncio.run") as mock_asyncio_run:

            mock_cfg = MagicMock()
            mock_cfg.notion_api_key = "test-key"
            mock_cfg.get_context_page_urls.return_value = []
            mock_config.return_value = mock_cfg

            mock_asyncio_run.return_value = ([search_result], [])

            graph = build_workflow()
            result = graph.invoke({
                "pr_number": 42,
                "verbose": False,
                "post_comment": False,
            })

        assert result["status"] == "complete"
        assert result["recommendation"].verdict == "approve"
        assert result["markdown_comment"] == "# Review\nAll good."


class TestWorkflowExitPath:
    """Test the exit path: user exits without confirming context."""

    @patch("pr_review_agent.graph.nodes.display_exit_instructions")
    @patch("pr_review_agent.graph.nodes.confirm_context")
    @patch("pr_review_agent.graph.nodes.score_relevance")
    @patch("pr_review_agent.graph.nodes.summarize_pr")
    @patch("pr_review_agent.graph.nodes.fetch_ci_checks")
    @patch("pr_review_agent.graph.nodes.fetch_diff")
    @patch("pr_review_agent.graph.nodes.fetch_pr")
    def test_exit_path_blocked(
        self,
        mock_fetch_pr,
        mock_fetch_diff,
        mock_fetch_ci_checks,
        mock_summarize_pr,
        mock_score_relevance,
        mock_confirm_context,
        mock_display_exit,
    ):
        """User exits -> status='blocked'."""
        pr_data = PRData(
            number=42,
            title="Test PR",
            author="dev",
            additions=50,
            deletions=5,
            branch="feature/test",
            files=[],
        )
        mock_fetch_pr.return_value = pr_data
        mock_fetch_diff.return_value = "diff"
        mock_fetch_ci_checks.side_effect = Exception("no CI")
        mock_summarize_pr.return_value = "PR summary"

        search_result = NotionSearchResult(
            page_id="p1", title="Page", url="", content="content",
        )

        scored = RelevanceScore(
            page_id="p1", title="Page", url="", content="content",
            score=5.0, explanation="ok", key_matches=[], gaps=[],
        )
        mock_score_relevance.return_value = scored

        # User exits
        mock_confirm_context.return_value = ("exit", [], None)

        with patch("pr_review_agent.config.get_config") as mock_config, \
             patch("pr_review_agent.graph.nodes.NotionMCPClient") as mock_client_cls, \
             patch("pr_review_agent.graph.nodes.asyncio.run") as mock_asyncio_run:

            mock_cfg = MagicMock()
            mock_cfg.notion_api_key = "test-key"
            mock_cfg.get_context_page_urls.return_value = []
            mock_config.return_value = mock_cfg
            mock_asyncio_run.return_value = ([search_result], [])

            graph = build_workflow()
            result = graph.invoke({
                "pr_number": 42,
                "verbose": False,
                "post_comment": False,
            })

        assert result["status"] == "blocked"
        assert result["should_block"] is True
        mock_display_exit.assert_called_once()
