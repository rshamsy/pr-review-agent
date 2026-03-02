"""Tests for the Typer CLI entry point."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import typer.testing
import pytest

from pr_review_agent.cli import app, _rewrite_args

runner = typer.testing.CliRunner()


# ===========================================================================
# Help / usage
# ===========================================================================


class TestCLIHelp:
    """Basic smoke-tests for help output."""

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 2)
        assert "Usage" in result.output or "usage" in result.output.lower()

    def test_help_flag_shows_usage(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "check-config" in result.output
        assert "review" in result.output.lower()

    def test_review_help_shows_options(self) -> None:
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        assert "--post" in result.output
        assert "--verbose" in result.output
        assert "--model" in result.output
        assert "PR_NUMBER" in result.output or "pr_number" in result.output.lower()


# ===========================================================================
# _rewrite_args — bare number shortcut
# ===========================================================================


class TestRewriteArgs:
    """Test that _rewrite_args() injects 'review' for bare PR numbers."""

    def test_bare_number_inserts_review(self) -> None:
        with patch("pr_review_agent.cli.sys") as mock_sys:
            mock_sys.argv = ["pr-review", "42"]
            _rewrite_args()
            assert mock_sys.argv == ["pr-review", "review", "42"]

    def test_bare_number_with_flags(self) -> None:
        with patch("pr_review_agent.cli.sys") as mock_sys:
            mock_sys.argv = ["pr-review", "42", "--post", "--verbose"]
            _rewrite_args()
            assert mock_sys.argv == ["pr-review", "review", "42", "--post", "--verbose"]

    def test_explicit_review_not_doubled(self) -> None:
        with patch("pr_review_agent.cli.sys") as mock_sys:
            mock_sys.argv = ["pr-review", "review", "42"]
            _rewrite_args()
            assert mock_sys.argv == ["pr-review", "review", "42"]

    def test_check_config_not_rewritten(self) -> None:
        with patch("pr_review_agent.cli.sys") as mock_sys:
            mock_sys.argv = ["pr-review", "check-config"]
            _rewrite_args()
            assert mock_sys.argv == ["pr-review", "check-config"]

    def test_help_not_rewritten(self) -> None:
        with patch("pr_review_agent.cli.sys") as mock_sys:
            mock_sys.argv = ["pr-review", "--help"]
            _rewrite_args()
            assert mock_sys.argv == ["pr-review", "--help"]

    def test_no_args_not_rewritten(self) -> None:
        with patch("pr_review_agent.cli.sys") as mock_sys:
            mock_sys.argv = ["pr-review"]
            _rewrite_args()
            assert mock_sys.argv == ["pr-review"]

    def test_non_numeric_not_rewritten(self) -> None:
        with patch("pr_review_agent.cli.sys") as mock_sys:
            mock_sys.argv = ["pr-review", "foobar"]
            _rewrite_args()
            assert mock_sys.argv == ["pr-review", "foobar"]


# ===========================================================================
# check-config command
# ===========================================================================


class TestCheckConfig:
    """Tests for the check-config subcommand."""

    @patch("pr_review_agent.config.validate_config")
    def test_check_config_no_errors(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = []
        result = runner.invoke(app, ["check-config"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "All configuration" in result.output

    @patch("pr_review_agent.config.validate_config")
    def test_check_config_with_errors(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = [
            "ANTHROPIC_API_KEY is not set",
            "NOTION_API_KEY is not set",
            "GitHub CLI (gh) is not installed.",
        ]
        result = runner.invoke(app, ["check-config"])
        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output
        assert "NOTION_API_KEY" in result.output

    @patch("pr_review_agent.config.validate_config")
    def test_check_config_single_error(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = ["npx is not installed."]
        result = runner.invoke(app, ["check-config"])
        assert result.exit_code == 1
        assert "npx" in result.output


# ===========================================================================
# review command
# ===========================================================================


class TestReviewCommand:
    """Tests for the main review command.

    Note: CliRunner calls app directly, so we use ["review", "39"].
    The shortcut `pr-review 39` works via _rewrite_args() tested above.
    """

    @patch("pr_review_agent.config.validate_config")
    @patch("pr_review_agent.config.get_config")
    def test_review_invokes_workflow(
        self,
        mock_get_config: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        mock_validate.return_value = []
        config_obj = MagicMock()
        config_obj.pr_review_model = "claude-sonnet-4-20250514"
        mock_get_config.return_value = config_obj

        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {"status": "complete"}

        with patch("pr_review_agent.graph.workflow.build_workflow", return_value=mock_workflow):
            result = runner.invoke(app, ["review", "39"])

        assert result.exit_code == 0

    @patch("pr_review_agent.config.validate_config")
    @patch("pr_review_agent.config.get_config")
    def test_review_with_post_flag(
        self,
        mock_get_config: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        mock_validate.return_value = []
        config_obj = MagicMock()
        config_obj.pr_review_model = "claude-sonnet-4-20250514"
        mock_get_config.return_value = config_obj

        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {"status": "complete"}

        with patch("pr_review_agent.graph.workflow.build_workflow", return_value=mock_workflow):
            result = runner.invoke(app, ["review", "39", "--post"])

        mock_workflow.invoke.assert_called_once()
        call_args = mock_workflow.invoke.call_args[0][0]
        assert call_args["post_comment"] is True
        assert call_args["pr_number"] == 39

    @patch("pr_review_agent.config.validate_config")
    @patch("pr_review_agent.config.get_config")
    def test_review_with_verbose_flag(
        self,
        mock_get_config: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        mock_validate.return_value = []
        config_obj = MagicMock()
        config_obj.pr_review_model = "claude-sonnet-4-20250514"
        mock_get_config.return_value = config_obj

        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {"status": "complete"}

        with patch("pr_review_agent.graph.workflow.build_workflow", return_value=mock_workflow):
            result = runner.invoke(app, ["review", "39", "--verbose"])

        mock_workflow.invoke.assert_called_once()
        call_args = mock_workflow.invoke.call_args[0][0]
        assert call_args["verbose"] is True

    @patch("pr_review_agent.config.validate_config")
    @patch("pr_review_agent.config.get_config")
    def test_review_blocked_status_exits_with_code_1(
        self,
        mock_get_config: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        mock_validate.return_value = []
        config_obj = MagicMock()
        config_obj.pr_review_model = "claude-sonnet-4-20250514"
        mock_get_config.return_value = config_obj

        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {"status": "blocked"}

        with patch("pr_review_agent.graph.workflow.build_workflow", return_value=mock_workflow):
            result = runner.invoke(app, ["review", "39"])

        assert result.exit_code == 1

    @patch("pr_review_agent.config.validate_config")
    @patch("pr_review_agent.config.get_config")
    def test_review_workflow_exception_exits_with_code_1(
        self,
        mock_get_config: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        mock_validate.return_value = []
        config_obj = MagicMock()
        config_obj.pr_review_model = "claude-sonnet-4-20250514"
        mock_get_config.return_value = config_obj

        mock_workflow = MagicMock()
        mock_workflow.invoke.side_effect = RuntimeError("Network error")

        with patch("pr_review_agent.graph.workflow.build_workflow", return_value=mock_workflow):
            result = runner.invoke(app, ["review", "39"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_review_missing_api_keys_exits_with_code_1(self) -> None:
        with patch(
            "pr_review_agent.config.validate_config",
            return_value=["ANTHROPIC_API_KEY is not set"],
        ), patch(
            "pr_review_agent.config.get_config",
            return_value=MagicMock(pr_review_model="claude-sonnet-4-20250514"),
        ):
            result = runner.invoke(app, ["review", "39"])

        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output

    def test_review_missing_notion_key_exits_with_code_1(self) -> None:
        with patch(
            "pr_review_agent.config.validate_config",
            return_value=["NOTION_API_KEY is not set"],
        ), patch(
            "pr_review_agent.config.get_config",
            return_value=MagicMock(pr_review_model="claude-sonnet-4-20250514"),
        ):
            result = runner.invoke(app, ["review", "39"])

        assert result.exit_code == 1

    def test_review_non_critical_errors_allow_proceed(self) -> None:
        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {"status": "complete"}

        with patch(
            "pr_review_agent.config.validate_config",
            return_value=["GitHub CLI (gh) is not installed."],
        ), patch(
            "pr_review_agent.config.get_config",
            return_value=MagicMock(pr_review_model="claude-sonnet-4-20250514"),
        ), patch(
            "pr_review_agent.graph.workflow.build_workflow",
            return_value=mock_workflow,
        ):
            result = runner.invoke(app, ["review", "39"])

        assert result.exit_code == 0

    @patch("pr_review_agent.config.validate_config")
    @patch("pr_review_agent.config.get_config")
    def test_review_custom_model_option(
        self,
        mock_get_config: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        mock_validate.return_value = []
        config_obj = MagicMock()
        config_obj.pr_review_model = "claude-sonnet-4-20250514"
        mock_get_config.return_value = config_obj

        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {"status": "complete"}

        with patch("pr_review_agent.graph.workflow.build_workflow", return_value=mock_workflow):
            result = runner.invoke(app, ["review", "39", "--model", "claude-opus-4-20250514"])

        mock_workflow.invoke.assert_called_once()
        call_args = mock_workflow.invoke.call_args[0][0]
        assert call_args["model"] == "claude-opus-4-20250514"
