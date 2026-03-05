"""Tests for pr_review_agent.notion.relevance — relevance scoring and extraction with Claude.

Mocks ChatAnthropic to avoid real LLM calls.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.models.notion import RelevanceScore
from pr_review_agent.notion.relevance import extract_relevant_sections, score_relevance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm_response(content: str) -> MagicMock:
    """Create a mock LLM response with the given content string."""
    response = MagicMock()
    response.content = content
    return response


# ---------------------------------------------------------------------------
# Tests for extract_relevant_sections
# ---------------------------------------------------------------------------

class TestExtractRelevantSections:
    """Tests for extract_relevant_sections()."""

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_returns_relevant_text(self, mock_chat_cls):
        """When Haiku finds relevant content, it returns the extracted text."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response("## Standup Notes\n- Fixed payment bug")
        mock_chat_cls.return_value = mock_llm

        result = extract_relevant_sections(
            pr_summary="Fix payment tracking bug",
            page_content="## Standup Notes\n- Fixed payment bug\n## Other\n- Unrelated stuff",
            page_title="Standup Notes",
        )

        assert result is not None
        assert "payment bug" in result

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_returns_none_when_not_relevant(self, mock_chat_cls):
        """When Haiku responds with NONE, returns None."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response("NONE")
        mock_chat_cls.return_value = mock_llm

        result = extract_relevant_sections(
            pr_summary="Fix payment tracking bug",
            page_content="## Meeting Notes\n- Discussed lunch plans",
            page_title="Random Notes",
        )

        assert result is None

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_returns_none_for_empty_page(self, mock_chat_cls):
        """Empty page content returns None without calling LLM."""
        result = extract_relevant_sections(
            pr_summary="Fix something",
            page_content="",
        )

        assert result is None
        mock_chat_cls.assert_not_called()

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_returns_none_for_whitespace_only_page(self, mock_chat_cls):
        """Whitespace-only page content returns None without calling LLM."""
        result = extract_relevant_sections(
            pr_summary="Fix something",
            page_content="   \n  \t  ",
        )

        assert result is None
        mock_chat_cls.assert_not_called()

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_uses_specified_model(self, mock_chat_cls):
        """The model parameter is forwarded to ChatAnthropic."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response("NONE")
        mock_chat_cls.return_value = mock_llm

        extract_relevant_sections(
            pr_summary="test",
            page_content="some content",
            model="claude-sonnet-4-20250514",
        )

        mock_chat_cls.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0,
        )

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_case_insensitive_none_response(self, mock_chat_cls):
        """Case variations of NONE are treated as no relevant content."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response("  none  ")
        mock_chat_cls.return_value = mock_llm

        result = extract_relevant_sections(
            pr_summary="test",
            page_content="some content",
        )

        assert result is None


# ---------------------------------------------------------------------------
# Tests for score_relevance
# ---------------------------------------------------------------------------

class TestScoreRelevance:
    """Tests for score_relevance()."""

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_high_relevance_score(self, mock_chat_cls):
        """When LLM scores a page as highly relevant (9/10)."""
        llm_response = json.dumps({
            "score": 9,
            "explanation": "This page clearly describes the payment tracking feature.",
            "key_matches": ["payment tracking", "CSV export"],
            "gaps": [],
            "relevant_excerpts": ["Supplier payments must be tracked with CSV export capability."],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="Add supplier payment tracking with CSV export",
            notion_content="Feature: Supplier Payment Tracking\nRequirements: ...",
            notion_page_id="page-123",
            notion_title="Payment Tracking",
            notion_url="https://notion.so/payment",
        )

        assert isinstance(result, RelevanceScore)
        assert result.score == 9.0
        assert result.page_id == "page-123"
        assert result.title == "Payment Tracking"
        assert result.url == "https://notion.so/payment"
        assert "payment tracking" in result.key_matches
        assert result.gaps == []
        assert "payment tracking feature" in result.explanation
        assert result.relevant_excerpts == ["Supplier payments must be tracked with CSV export capability."]

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_low_relevance_score(self, mock_chat_cls):
        """When LLM scores a page as not relevant (2/10)."""
        llm_response = json.dumps({
            "score": 2,
            "explanation": "This page is about onboarding, not payments.",
            "key_matches": [],
            "gaps": ["payment tracking", "CSV export"],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="Add supplier payment tracking",
            notion_content="Onboarding guide for new employees...",
            notion_page_id="page-456",
            notion_title="Onboarding Guide",
        )

        assert result.score == 2.0
        assert len(result.gaps) == 2
        assert result.key_matches == []

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_score_clamped_to_valid_range(self, mock_chat_cls):
        """Scores are clamped to [0, 10]."""
        llm_response = json.dumps({
            "score": 15,  # above max
            "explanation": "Extremely relevant",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="test",
            notion_content="test content",
        )

        assert result.score == 10.0

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_negative_score_clamped_to_zero(self, mock_chat_cls):
        """Negative scores are clamped to 0."""
        llm_response = json.dumps({
            "score": -5,
            "explanation": "Not relevant at all",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="test",
            notion_content="test content",
        )

        assert result.score == 0.0

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_json_parsing_failure_with_embedded_json(self, mock_chat_cls):
        """When response has extra text around JSON, the JSON is still extracted."""
        llm_response = 'Here is the score:\n{"score": 7, "explanation": "Relevant", "key_matches": ["feature"], "gaps": []}\nDone.'
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="test",
            notion_content="test content",
        )

        assert result.score == 7.0
        assert result.explanation == "Relevant"

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_json_parsing_total_failure(self, mock_chat_cls):
        """When response contains no valid JSON, defaults to score 0."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response("I cannot parse this request.")
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="test",
            notion_content="test content",
        )

        assert result.score == 0.0
        assert "Failed to parse" in result.explanation

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_preserves_notion_content_in_result(self, mock_chat_cls):
        """The original notion_content is stored in the result."""
        llm_response = json.dumps({
            "score": 5,
            "explanation": "Moderate match",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="test",
            notion_content="Original full content of the page",
            notion_page_id="pid",
            notion_title="Title",
            notion_url="https://notion.so/url",
        )

        assert result.content == "Original full content of the page"

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_llm_receives_correct_messages(self, mock_chat_cls):
        """Verify the LLM is invoked with system + human messages containing the content."""
        llm_response = json.dumps({
            "score": 5,
            "explanation": "ok",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        score_relevance(
            pr_summary="My PR summary",
            notion_content="My notion content",
            notion_title="My Title",
        )

        # Check that invoke was called with 2 messages
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2
        # System message
        assert "relevance scoring" in call_args[0].content.lower()
        # Human message contains our inputs
        assert "My PR summary" in call_args[1].content
        assert "My notion content" in call_args[1].content
        assert "My Title" in call_args[1].content

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_content_truncation(self, mock_chat_cls):
        """Notion content longer than 8000 chars is truncated before sending to LLM."""
        llm_response = json.dumps({
            "score": 5,
            "explanation": "ok",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        long_content = "x" * 20_000

        score_relevance(
            pr_summary="test",
            notion_content=long_content,
        )

        # The human message should contain truncated content (8000 chars max)
        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        # The full 20000-char content should not appear in the message
        assert "x" * 20_000 not in human_msg
        # But 8000 x's should be there
        assert "x" * 8000 in human_msg

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_uses_specified_model(self, mock_chat_cls):
        """The model parameter is forwarded to ChatAnthropic."""
        llm_response = json.dumps({
            "score": 5,
            "explanation": "ok",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        score_relevance(
            pr_summary="test",
            notion_content="test",
            model="claude-sonnet-4-20250514",
        )

        mock_chat_cls.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            temperature=0,
        )

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_missing_score_key_defaults_to_zero(self, mock_chat_cls):
        """When 'score' key is missing from JSON, defaults to 0."""
        llm_response = json.dumps({
            "explanation": "no score provided",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="test",
            notion_content="test",
        )

        assert result.score == 0.0

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_relevant_excerpts_parsed(self, mock_chat_cls):
        """Relevant excerpts are parsed from the LLM JSON response."""
        llm_response = json.dumps({
            "score": 8,
            "explanation": "Highly relevant page.",
            "key_matches": ["auth flow"],
            "gaps": [],
            "relevant_excerpts": [
                "Users must authenticate via OAuth2 before accessing the dashboard.",
                "Session tokens expire after 24 hours.",
            ],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="Add OAuth2 authentication",
            notion_content="Auth spec content...",
            notion_page_id="page-auth",
            notion_title="Auth Spec",
        )

        assert result.relevant_excerpts == [
            "Users must authenticate via OAuth2 before accessing the dashboard.",
            "Session tokens expire after 24 hours.",
        ]

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_missing_relevant_excerpts_defaults_to_empty(self, mock_chat_cls):
        """When relevant_excerpts is missing from JSON, defaults to empty list."""
        llm_response = json.dumps({
            "score": 5,
            "explanation": "Moderate match",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(llm_response)
        mock_chat_cls.return_value = mock_llm

        result = score_relevance(
            pr_summary="test",
            notion_content="test content",
        )

        assert result.relevant_excerpts == []

    @patch("pr_review_agent.notion.relevance.ChatAnthropic")
    def test_response_content_as_list_raises(self, mock_chat_cls):
        """When response.content is a list, str() produces single-quoted Python repr.

        The source code's fallback extractor finds ``{`` and ``}`` in the
        str() output, but the extracted substring uses single quotes (Python
        repr of a dict) which is not valid JSON. The second json.loads call
        also fails, raising JSONDecodeError because the outer try/except
        only catches the first json.loads, while the fallback json.loads
        is unguarded.
        """
        inner_json = json.dumps({
            "score": 6,
            "explanation": "ok",
            "key_matches": [],
            "gaps": [],
        })
        mock_llm = MagicMock()
        response = MagicMock()
        response.content = [{"type": "text", "text": inner_json}]
        mock_llm.invoke.return_value = response
        mock_chat_cls.return_value = mock_llm

        # The source code does not handle this case gracefully — the fallback
        # extraction finds { and } but the substring is single-quoted Python
        # repr, causing a second unguarded json.loads to raise.
        with pytest.raises(json.JSONDecodeError):
            score_relevance(
                pr_summary="test",
                notion_content="test",
            )
