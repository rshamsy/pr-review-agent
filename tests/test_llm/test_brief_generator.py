"""Tests for pr_review_agent.llm.brief_generator — LLM-based PR summarization and review brief generation.

Mocks ChatAnthropic.invoke() to avoid real LLM calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.llm.brief_generator import MAX_DIFF_CHARS, generate_brief, summarize_pr
from pr_review_agent.models.brief import ReviewBrief
from pr_review_agent.models.notion import NotionContext
from pr_review_agent.models.pr import FileChange, PRAnalysis, PRData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pr_data() -> PRData:
    return PRData(
        number=42,
        title="Add supplier payment tracking",
        author="dev-user",
        additions=500,
        deletions=20,
        branch="feature/payments",
        files=[
            FileChange(
                filename="lib/services/payment-service.ts",
                status="added",
                additions=200,
                deletions=0,
            ),
            FileChange(
                filename="lib/services/csv-export.ts",
                status="added",
                additions=100,
                deletions=0,
            ),
        ],
    )


@pytest.fixture
def notion_context() -> NotionContext:
    return NotionContext(
        page_id="notion-page-1",
        page_url="https://notion.so/page-1",
        title="Payment Tracking Feature",
        description="Track supplier payments with CSV export",
        requirements=["Payment tracking", "CSV export", "Decimal precision"],
        raw_content="Full content of the Notion page...",
    )


@pytest.fixture
def analysis() -> PRAnalysis:
    return PRAnalysis(
        classification="major",
        services=[],
        api_routes=[],
        ui_changes=[],
        test_files=[],
        risks=[],
        missing_tests=[],
        total_additions=500,
        total_deletions=20,
    )


@pytest.fixture
def valid_brief_json() -> str:
    """A valid JSON string matching ReviewBrief schema."""
    return json.dumps({
        "summary": "This PR adds supplier payment tracking with CSV export.",
        "what_was_requested": ["Payment tracking", "CSV export"],
        "what_was_implemented": ["Payment service", "CSV export service"],
        "deltas": [
            {
                "aspect": "Payment tracking",
                "intended": "Track payments per supplier",
                "implemented": "Payment service created",
                "status": "match",
            },
        ],
        "llm_recommendation": "approve",
        "llm_confidence": 0.85,
        "key_concerns": [],
        "positive_findings": ["Clean architecture"],
    })


# ---------------------------------------------------------------------------
# Tests for summarize_pr
# ---------------------------------------------------------------------------

class TestSummarizePr:
    """Tests for summarize_pr()."""

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_returns_string_summary(self, mock_chat_cls, pr_data):
        """summarize_pr returns a string summary from the LLM."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This PR adds payment tracking for suppliers."
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        result = summarize_pr(pr_data, "diff text here")

        assert isinstance(result, str)
        assert "payment tracking" in result.lower()

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_passes_pr_metadata_to_llm(self, mock_chat_cls, pr_data):
        """The LLM receives PR metadata (number, title, branch, etc.)."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary text"
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        summarize_pr(pr_data, "the diff content")

        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2  # System + Human messages
        human_msg = call_args[1].content
        assert "42" in human_msg  # PR number
        assert "Add supplier payment tracking" in human_msg
        assert "feature/payments" in human_msg

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_diff_preview_truncated_to_4000(self, mock_chat_cls, pr_data):
        """Only the first 4000 chars of diff are included in the summary prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary"
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        long_diff = "x" * 10_000
        summarize_pr(pr_data, long_diff)

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        # Should not contain the full 10000 chars
        assert "x" * 10_000 not in human_msg
        # Should contain at most 4000 x's in sequence
        assert "x" * 4000 in human_msg

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_uses_specified_model(self, mock_chat_cls, pr_data):
        """The model parameter is forwarded to ChatAnthropic."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary"
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        summarize_pr(pr_data, "diff", model="claude-opus-4-20250514")

        mock_chat_cls.assert_called_once_with(
            model="claude-opus-4-20250514",
            max_tokens=256,
            temperature=0,
        )

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_handles_non_string_response_content(self, mock_chat_cls, pr_data):
        """When response.content is not a string, it is converted via str()."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = ["text block"]  # Not a string
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        result = summarize_pr(pr_data, "diff")

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests for generate_brief
# ---------------------------------------------------------------------------

class TestGenerateBrief:
    """Tests for generate_brief()."""

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_returns_valid_review_brief(
        self, mock_chat_cls, notion_context, pr_data, analysis, valid_brief_json
    ):
        """generate_brief returns a valid ReviewBrief from LLM JSON."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_brief_json
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        result = generate_brief(notion_context, pr_data, analysis, "diff text")

        assert isinstance(result, ReviewBrief)
        assert result.summary == "This PR adds supplier payment tracking with CSV export."
        assert result.llm_recommendation == "approve"
        assert result.llm_confidence == 0.85
        assert len(result.deltas) == 1
        assert result.deltas[0].status == "match"
        assert "Clean architecture" in result.positive_findings

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_diff_truncation_with_very_long_diff(
        self, mock_chat_cls, notion_context, pr_data, analysis, valid_brief_json
    ):
        """Very long diffs are truncated to MAX_DIFF_CHARS with a truncation notice."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_brief_json
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        long_diff = "a" * (MAX_DIFF_CHARS + 10_000)
        generate_brief(notion_context, pr_data, analysis, long_diff)

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        # Should contain truncation notice
        assert "truncated" in human_msg
        assert "10000 chars omitted" in human_msg
        # Should NOT contain the full long diff
        assert "a" * (MAX_DIFF_CHARS + 10_000) not in human_msg

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_diff_not_truncated_when_short(
        self, mock_chat_cls, notion_context, pr_data, analysis, valid_brief_json
    ):
        """Short diffs are not truncated."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_brief_json
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        short_diff = "short diff content"
        generate_brief(notion_context, pr_data, analysis, short_diff)

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        assert "truncated" not in human_msg
        assert "short diff content" in human_msg

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_json_parsing_failure_with_embedded_json(
        self, mock_chat_cls, notion_context, pr_data, analysis
    ):
        """When LLM wraps JSON in extra text, the JSON is still extracted."""
        brief_data = {
            "summary": "Extracted brief",
            "what_was_requested": [],
            "what_was_implemented": [],
            "deltas": [],
            "llm_recommendation": "needs_discussion",
            "llm_confidence": 0.5,
            "key_concerns": ["concern"],
            "positive_findings": [],
        }
        response_text = f"Here is the review:\n{json.dumps(brief_data)}\n\nEnd of review."

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = response_text
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        result = generate_brief(notion_context, pr_data, analysis, "diff")

        assert isinstance(result, ReviewBrief)
        assert result.summary == "Extracted brief"
        assert result.llm_recommendation == "needs_discussion"

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_json_parsing_total_failure_returns_fallback(
        self, mock_chat_cls, notion_context, pr_data, analysis
    ):
        """When LLM returns completely unparseable text, a fallback brief is returned."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is not JSON at all and has no braces"
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        result = generate_brief(notion_context, pr_data, analysis, "diff")

        assert isinstance(result, ReviewBrief)
        assert "Failed to parse" in result.summary
        assert result.llm_recommendation == "needs_discussion"
        assert result.llm_confidence == 0.0
        assert "LLM response parsing failed" in result.key_concerns

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_passes_notion_context_to_llm(
        self, mock_chat_cls, notion_context, pr_data, analysis, valid_brief_json
    ):
        """The LLM receives Notion context details (title, description, requirements)."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_brief_json
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        generate_brief(notion_context, pr_data, analysis, "diff")

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        assert "Payment Tracking Feature" in human_msg
        assert "Track supplier payments with CSV export" in human_msg
        assert "Payment tracking" in human_msg

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_uses_specified_model(
        self, mock_chat_cls, notion_context, pr_data, analysis, valid_brief_json
    ):
        """The model parameter is forwarded to ChatAnthropic."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_brief_json
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        generate_brief(
            notion_context, pr_data, analysis, "diff",
            model="claude-opus-4-20250514",
        )

        mock_chat_cls.assert_called_once_with(
            model="claude-opus-4-20250514",
            max_tokens=4096,
            temperature=0,
        )

    @patch("pr_review_agent.llm.brief_generator.ChatAnthropic")
    def test_passes_analysis_details_to_llm(
        self, mock_chat_cls, notion_context, pr_data, valid_brief_json
    ):
        """The LLM receives analysis classification and formatted summaries."""
        from pr_review_agent.models.pr import ServiceChangeInfo, APIRouteInfo

        analysis = PRAnalysis(
            classification="major",
            services=[
                ServiceChangeInfo(
                    path="lib/services/pay.ts",
                    basename="pay",
                    is_new=True,
                    lines_changed=100,
                ),
            ],
            api_routes=[
                APIRouteInfo(
                    path="app/api/pay/route.ts",
                    endpoint="/pay",
                    methods=["GET", "POST"],
                ),
            ],
            ui_changes=[],
            test_files=[],
            risks=[],
            missing_tests=[],
            total_additions=200,
            total_deletions=10,
        )

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_brief_json
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        generate_brief(notion_context, pr_data, analysis, "diff")

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        assert "major" in human_msg
        assert "pay" in human_msg
        assert "/pay" in human_msg
        assert "GET" in human_msg
