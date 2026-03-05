"""Tests for pr_review_agent.notion.context_loop — interactive context confirmation.

Mocks rich.prompt.Prompt.ask to simulate user input without a terminal.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from rich.panel import Panel

from pr_review_agent.models.notion import NotionContext, RelevanceScore
from pr_review_agent.notion.context_loop import confirm_context, display_exit_instructions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_scored_results(count: int = 1) -> list[RelevanceScore]:
    """Create a list of RelevanceScore objects for testing."""
    results = []
    for i in range(count):
        results.append(RelevanceScore(
            page_id=f"page-{i}",
            title=f"Test Page {i}",
            url=f"https://notion.so/page-{i}",
            content=f"Content for page {i}. " * 50,  # ~1000 chars
            score=float(9 - i),
            explanation=f"Explanation for page {i}",
            key_matches=[f"match-{i}-a", f"match-{i}-b"],
            gaps=[f"gap-{i}-a"],
            relevant_excerpts=[f"Excerpt from page {i} about the feature."],
        ))
    return results


# ---------------------------------------------------------------------------
# Test "confirmed" path — single select
# ---------------------------------------------------------------------------

class TestConfirmedPath:
    """User selects '1' to confirm the top Notion result."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_confirmed_returns_context_list(self, mock_console, mock_ask):
        """Selecting '1' returns ('confirmed', [NotionContext], None)."""
        scored = _make_scored_results(2)
        choice, contexts, url = confirm_context(scored)

        assert choice == "confirmed"
        assert isinstance(contexts, list)
        assert len(contexts) == 1
        assert isinstance(contexts[0], NotionContext)
        assert url is None

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_confirmed_context_has_correct_fields(self, mock_console, mock_ask):
        """The returned NotionContext is populated from the top scored result."""
        scored = _make_scored_results(1)
        choice, contexts, url = confirm_context(scored)

        ctx = contexts[0]
        assert ctx.page_id == "page-0"
        assert ctx.page_url == "https://notion.so/page-0"
        assert ctx.title == "Test Page 0"
        assert ctx.description == "Explanation for page 0"
        assert ctx.requirements == ["match-0-a", "match-0-b"]
        assert "Content for page 0" in ctx.raw_content


# ---------------------------------------------------------------------------
# Test multi-select path
# ---------------------------------------------------------------------------

class TestMultiSelectPath:
    """User selects multiple pages like '1,2'."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1,2")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_multi_select_returns_multiple_contexts(self, mock_console, mock_ask):
        """Selecting '1,2' returns two NotionContext objects."""
        scored = _make_scored_results(3)
        choice, contexts, url = confirm_context(scored)

        assert choice == "confirmed"
        assert len(contexts) == 2
        assert contexts[0].page_id == "page-0"
        assert contexts[1].page_id == "page-1"
        assert url is None

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="2,3")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_multi_select_non_first_results(self, mock_console, mock_ask):
        """Selecting '2,3' returns the 2nd and 3rd results."""
        scored = _make_scored_results(3)
        choice, contexts, url = confirm_context(scored)

        assert choice == "confirmed"
        assert len(contexts) == 2
        assert contexts[0].page_id == "page-1"
        assert contexts[1].page_id == "page-2"

    @patch("pr_review_agent.notion.context_loop.Prompt.ask")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_multi_select_invalid_index_retries(self, mock_console, mock_ask):
        """Invalid index (e.g. 0 or out-of-range) causes retry."""
        # First ask returns invalid "0", second returns valid "1"
        mock_ask.side_effect = ["0", "1"]
        scored = _make_scored_results(2)
        choice, contexts, url = confirm_context(scored)

        assert choice == "confirmed"
        assert len(contexts) == 1
        assert contexts[0].page_id == "page-0"

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1,1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_multi_select_deduplicates(self, mock_console, mock_ask):
        """Duplicate indices are deduplicated."""
        scored = _make_scored_results(2)
        choice, contexts, url = confirm_context(scored)

        assert choice == "confirmed"
        assert len(contexts) == 1
        assert contexts[0].page_id == "page-0"


# ---------------------------------------------------------------------------
# Test letter choices: s, u, x
# ---------------------------------------------------------------------------

class TestLetterChoices:
    """User enters s, u, or x."""

    @patch("builtins.input", return_value="")  # simulate pressing Enter
    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="s")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_s_returns_partial(self, mock_console, mock_ask, mock_input):
        """Entering 's' returns ('partial', [], None)."""
        scored = _make_scored_results(1)
        choice, contexts, url = confirm_context(scored)

        assert choice == "partial"
        assert contexts == []
        assert url is None

    @patch("pr_review_agent.notion.context_loop.Prompt.ask")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_u_returns_provide_url(self, mock_console, mock_ask):
        """Entering 'u' then a URL returns ('provide_url', [], url)."""
        mock_ask.side_effect = ["u", "https://notion.so/my-page"]
        scored = _make_scored_results(1)

        choice, contexts, url = confirm_context(scored)

        assert choice == "provide_url"
        assert contexts == []
        assert url == "https://notion.so/my-page"

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="x")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_x_returns_exit(self, mock_console, mock_ask):
        """Entering 'x' returns ('exit', [], None)."""
        scored = _make_scored_results(1)
        choice, contexts, url = confirm_context(scored)

        assert choice == "exit"
        assert contexts == []
        assert url is None


# ---------------------------------------------------------------------------
# Test with empty scored_results (no results found)
# ---------------------------------------------------------------------------

class TestEmptyResults:
    """No Notion results found."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="x")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_no_results_exit(self, mock_console, mock_ask):
        """With empty results and choice 'x', returns ('exit', [], None)."""
        choice, contexts, url = confirm_context([])

        assert choice == "exit"
        assert contexts == []
        assert url is None

    @patch("pr_review_agent.notion.context_loop.Prompt.ask")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_no_results_provide_url(self, mock_console, mock_ask):
        """With empty results and choice 'u', user can provide a URL."""
        mock_ask.side_effect = ["u", "https://notion.so/custom-page"]

        choice, contexts, url = confirm_context([])

        assert choice == "provide_url"
        assert contexts == []
        assert url == "https://notion.so/custom-page"

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="x")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_no_results_displays_panel(self, mock_console, mock_ask):
        """When no results, a panel is displayed to the user."""
        confirm_context([])
        # Verify console.print was called (at least for the panel)
        assert mock_console.print.called


# ---------------------------------------------------------------------------
# Test display_exit_instructions
# ---------------------------------------------------------------------------

class TestDisplayExitInstructions:
    """Tests for display_exit_instructions()."""

    @patch("pr_review_agent.notion.context_loop.console")
    def test_displays_instructions(self, mock_console):
        """display_exit_instructions prints an instruction panel."""
        display_exit_instructions()

        assert mock_console.print.called
        # Verify a Panel was printed
        call_args = mock_console.print.call_args
        assert isinstance(call_args[0][0], Panel)


# ---------------------------------------------------------------------------
# Test multiple results display
# ---------------------------------------------------------------------------

class TestMultipleResults:
    """When multiple scored results are provided."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_multiple_results_confirmed_uses_top(self, mock_console, mock_ask):
        """With multiple results, confirming '1' uses the highest-scored result."""
        scored = _make_scored_results(3)
        choice, contexts, url = confirm_context(scored)

        assert choice == "confirmed"
        assert len(contexts) == 1
        assert contexts[0].page_id == "page-0"  # top result
        assert contexts[0].title == "Test Page 0"

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_all_results_display_url_and_explanation(self, mock_console, mock_ask):
        """All results (not just #1) display URL, explanation, and excerpts."""
        scored = _make_scored_results(3)
        confirm_context(scored)

        # Collect all printed Panel content
        panel_contents = []
        for call_args in mock_console.print.call_args_list:
            if call_args[0] and isinstance(call_args[0][0], Panel):
                renderable = call_args[0][0].renderable
                if isinstance(renderable, str):
                    panel_contents.append(renderable)

        # Should have 3 result panels
        assert len(panel_contents) == 3

        # Each panel should contain URL, explanation, and excerpts
        for i, content in enumerate(panel_contents):
            assert f"https://notion.so/page-{i}" in content
            assert f"Explanation for page {i}" in content
            assert f"Excerpt from page {i}" in content

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_results_display_key_matches_and_gaps(self, mock_console, mock_ask):
        """All results show key matches and gaps."""
        scored = _make_scored_results(2)
        confirm_context(scored)

        panel_contents = []
        for call_args in mock_console.print.call_args_list:
            if call_args[0] and isinstance(call_args[0][0], Panel):
                renderable = call_args[0][0].renderable
                if isinstance(renderable, str):
                    panel_contents.append(renderable)

        assert len(panel_contents) == 2
        for i, content in enumerate(panel_contents):
            assert f"match-{i}-a" in content
            assert f"gap-{i}-a" in content
