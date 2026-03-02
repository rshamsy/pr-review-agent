"""Tests for pr_review_agent.notion.context_loop — interactive context confirmation.

Mocks rich.prompt.Prompt.ask to simulate user input without a terminal.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

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
        ))
    return results


# ---------------------------------------------------------------------------
# Test "confirmed" path
# ---------------------------------------------------------------------------

class TestConfirmedPath:
    """User selects '1' to confirm the top Notion result."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_confirmed_returns_context(self, mock_console, mock_ask):
        """Selecting '1' returns ('confirmed', NotionContext, None)."""
        scored = _make_scored_results(2)
        choice, context, url = confirm_context(scored)

        assert choice == "confirmed"
        assert isinstance(context, NotionContext)
        assert url is None

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_confirmed_context_has_correct_fields(self, mock_console, mock_ask):
        """The returned NotionContext is populated from the top scored result."""
        scored = _make_scored_results(1)
        choice, context, url = confirm_context(scored)

        assert context.page_id == "page-0"
        assert context.page_url == "https://notion.so/page-0"
        assert context.title == "Test Page 0"
        assert context.description == "Explanation for page 0"
        assert context.requirements == ["match-0-a", "match-0-b"]
        assert "Content for page 0" in context.raw_content


# ---------------------------------------------------------------------------
# Test "provide_url" path
# ---------------------------------------------------------------------------

class TestProvideUrlPath:
    """User selects '3' to provide a specific Notion URL."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_provide_url_returns_url(self, mock_console, mock_ask):
        """Selecting '3' then entering a URL returns ('provide_url', None, url)."""
        # First call: choice selection, second call: URL input
        mock_ask.side_effect = ["3", "https://notion.so/my-page"]
        scored = _make_scored_results(1)

        choice, context, url = confirm_context(scored)

        assert choice == "provide_url"
        assert context is None
        assert url == "https://notion.so/my-page"


# ---------------------------------------------------------------------------
# Test "partial" path
# ---------------------------------------------------------------------------

class TestPartialPath:
    """User selects '2' to indicate partial context."""

    @patch("builtins.input", return_value="")  # simulate pressing Enter
    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="2")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_partial_returns_correctly(self, mock_console, mock_ask, mock_input):
        """Selecting '2' returns ('partial', None, None)."""
        scored = _make_scored_results(1)

        choice, context, url = confirm_context(scored)

        assert choice == "partial"
        assert context is None
        assert url is None


# ---------------------------------------------------------------------------
# Test "exit" path
# ---------------------------------------------------------------------------

class TestExitPath:
    """User selects '4' to exit without context."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="4")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_exit_returns_correctly(self, mock_console, mock_ask):
        """Selecting '4' returns ('exit', None, None)."""
        scored = _make_scored_results(1)

        choice, context, url = confirm_context(scored)

        assert choice == "exit"
        assert context is None
        assert url is None


# ---------------------------------------------------------------------------
# Test with empty scored_results (no results found)
# ---------------------------------------------------------------------------

class TestEmptyResults:
    """No Notion results found."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="4")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_no_results_exit(self, mock_console, mock_ask):
        """With empty results and choice '4', returns ('exit', None, None)."""
        choice, context, url = confirm_context([])

        assert choice == "exit"
        assert context is None
        assert url is None

    @patch("pr_review_agent.notion.context_loop.Prompt.ask")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_no_results_provide_url(self, mock_console, mock_ask):
        """With empty results and choice '3', user can provide a URL."""
        mock_ask.side_effect = ["3", "https://notion.so/custom-page"]

        choice, context, url = confirm_context([])

        assert choice == "provide_url"
        assert context is None
        assert url == "https://notion.so/custom-page"

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="4")
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
        from rich.panel import Panel
        assert isinstance(call_args[0][0], Panel)


# ---------------------------------------------------------------------------
# Test multiple results display
# ---------------------------------------------------------------------------

class TestMultipleResults:
    """When multiple scored results are provided."""

    @patch("pr_review_agent.notion.context_loop.Prompt.ask", return_value="1")
    @patch("pr_review_agent.notion.context_loop.console")
    def test_multiple_results_confirmed_uses_top(self, mock_console, mock_ask):
        """With multiple results, confirming uses the highest-scored result."""
        scored = _make_scored_results(3)
        choice, context, url = confirm_context(scored)

        assert choice == "confirmed"
        assert context.page_id == "page-0"  # top result
        assert context.title == "Test Page 0"
