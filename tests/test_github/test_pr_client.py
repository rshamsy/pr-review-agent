"""Tests for the GitHub PR client — subprocess-based gh CLI wrapper."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.github.pr_client import (
    _map_file_status,
    _run_gh,
    fetch_ci_checks,
    fetch_diff,
    fetch_pr,
)
from pr_review_agent.models.pr import CICheck, CIStatus, PRData


# ---------------------------------------------------------------------------
# Fixture data for gh CLI output
# ---------------------------------------------------------------------------

GH_PR_VIEW_JSON = json.dumps({
    "number": 39,
    "title": "Add supplier payment tracking",
    "author": {"login": "developer"},
    "additions": 682,
    "deletions": 35,
    "headRefName": "feature/supplier-payments",
    "files": [
        {"path": "lib/services/payment-service.ts", "additions": 200, "deletions": 0},
        {"path": "lib/services/csv-export.ts", "additions": 100, "deletions": 0},
        {"path": "app/api/supplier-payments/route.ts", "additions": 150, "deletions": 0},
        {"path": "app/payments/page.tsx", "additions": 120, "deletions": 0},
        {"path": "components/PaymentTable.tsx", "additions": 80, "deletions": 0},
        {"path": "prisma/migrations/20240101_add_payments/migration.sql", "additions": 30, "deletions": 0},
        {"path": "tests/lib/services/csv-export.test.ts", "additions": 50, "deletions": 0},
    ],
})

GH_PR_DIFF = """diff --git a/lib/services/payment-service.ts b/lib/services/payment-service.ts
new file mode 100644
--- /dev/null
+++ b/lib/services/payment-service.ts
@@ -0,0 +1,5 @@
+export function calculatePayment(amount: number, price: number) {
+  return amount * price;
+}
"""

GH_CI_CHECKS_JSON = json.dumps([
    {"name": "lint", "state": "COMPLETED", "conclusion": "SUCCESS"},
    {"name": "test", "state": "COMPLETED", "conclusion": "SUCCESS"},
    {"name": "build", "state": "COMPLETED", "conclusion": "SUCCESS"},
])


def _make_completed_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ===========================================================================
# _run_gh helper
# ===========================================================================


class TestRunGh:
    """Tests for the low-level _run_gh wrapper."""

    @patch("subprocess.run")
    def test_returns_stdout_on_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _make_completed_process(stdout="hello")
        assert _run_gh(["pr", "view", "1"]) == "hello"

    @patch("subprocess.run")
    def test_raises_on_nonzero_return_code(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _make_completed_process(
            returncode=1, stderr="not found"
        )
        with pytest.raises(RuntimeError, match="gh command failed"):
            _run_gh(["pr", "view", "999"])

    @patch("subprocess.run")
    def test_raises_on_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=30)
        with pytest.raises(subprocess.TimeoutExpired):
            _run_gh(["pr", "view", "1"])

    @patch("subprocess.run")
    def test_passes_correct_args(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _make_completed_process(stdout="ok")
        _run_gh(["pr", "view", "42", "--json", "number"])
        mock_run.assert_called_once_with(
            ["gh", "pr", "view", "42", "--json", "number"],
            capture_output=True,
            text=True,
            timeout=30,
        )


# ===========================================================================
# _map_file_status
# ===========================================================================


class TestMapFileStatus:
    """Tests for file status inference."""

    def test_added(self) -> None:
        assert _map_file_status(additions=10, deletions=0) == "added"

    def test_removed(self) -> None:
        assert _map_file_status(additions=0, deletions=5) == "removed"

    def test_modified(self) -> None:
        assert _map_file_status(additions=3, deletions=2) == "modified"

    def test_zero_both(self) -> None:
        # Edge case: no changes at all
        assert _map_file_status(additions=0, deletions=0) == "modified"


# ===========================================================================
# fetch_pr
# ===========================================================================


class TestFetchPR:
    """Tests for fetch_pr() with mocked gh CLI."""

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_returns_pr_data(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = GH_PR_VIEW_JSON
        pr = fetch_pr(39)

        assert isinstance(pr, PRData)
        assert pr.number == 39
        assert pr.title == "Add supplier payment tracking"
        assert pr.author == "developer"
        assert pr.additions == 682
        assert pr.deletions == 35
        assert pr.branch == "feature/supplier-payments"

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_parses_files(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = GH_PR_VIEW_JSON
        pr = fetch_pr(39)

        assert len(pr.files) == 7
        # First file should be payment-service.ts
        first = pr.files[0]
        assert first.filename == "lib/services/payment-service.ts"
        assert first.additions == 200
        assert first.deletions == 0
        assert first.status == "added"
        # Patch should be None (gh pr view --json doesn't include patches)
        assert first.patch is None

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_handles_missing_author(self, mock_gh: MagicMock) -> None:
        data = json.loads(GH_PR_VIEW_JSON)
        del data["author"]
        mock_gh.return_value = json.dumps(data)
        pr = fetch_pr(39)
        assert pr.author == "unknown"

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_handles_empty_files(self, mock_gh: MagicMock) -> None:
        data = json.loads(GH_PR_VIEW_JSON)
        data["files"] = []
        mock_gh.return_value = json.dumps(data)
        pr = fetch_pr(39)
        assert pr.files == []

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_handles_missing_files_key(self, mock_gh: MagicMock) -> None:
        data = json.loads(GH_PR_VIEW_JSON)
        del data["files"]
        mock_gh.return_value = json.dumps(data)
        pr = fetch_pr(39)
        assert pr.files == []

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_handles_missing_headRefName(self, mock_gh: MagicMock) -> None:
        data = json.loads(GH_PR_VIEW_JSON)
        del data["headRefName"]
        mock_gh.return_value = json.dumps(data)
        pr = fetch_pr(39)
        assert pr.branch == ""

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_file_status_detection(self, mock_gh: MagicMock) -> None:
        """Verify that file statuses are inferred from additions/deletions."""
        data = {
            "number": 1,
            "title": "Test",
            "author": {"login": "dev"},
            "additions": 10,
            "deletions": 5,
            "headRefName": "main",
            "files": [
                {"path": "new.ts", "additions": 10, "deletions": 0},
                {"path": "modified.ts", "additions": 5, "deletions": 3},
                {"path": "removed.ts", "additions": 0, "deletions": 8},
            ],
        }
        mock_gh.return_value = json.dumps(data)
        pr = fetch_pr(1)

        assert pr.files[0].status == "added"
        assert pr.files[1].status == "modified"
        assert pr.files[2].status == "removed"

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_raises_on_gh_failure(self, mock_gh: MagicMock) -> None:
        mock_gh.side_effect = RuntimeError("gh command failed: not found")
        with pytest.raises(RuntimeError, match="gh command failed"):
            fetch_pr(999)

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_raises_on_invalid_json(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = "not valid json {{"
        with pytest.raises(json.JSONDecodeError):
            fetch_pr(39)

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_calls_gh_with_correct_args(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = GH_PR_VIEW_JSON
        fetch_pr(42)
        mock_gh.assert_called_once_with([
            "pr", "view", "42",
            "--json", "number,title,author,additions,deletions,files,headRefName",
        ])


# ===========================================================================
# fetch_diff
# ===========================================================================


class TestFetchDiff:
    """Tests for fetch_diff() with mocked gh CLI."""

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_returns_diff_string(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = GH_PR_DIFF
        diff = fetch_diff(39)
        assert isinstance(diff, str)
        assert "calculatePayment" in diff
        assert "diff --git" in diff

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_returns_empty_diff(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = ""
        diff = fetch_diff(39)
        assert diff == ""

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_calls_gh_with_correct_args(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = GH_PR_DIFF
        fetch_diff(42)
        mock_gh.assert_called_once_with(
            ["pr", "diff", "42"],
            timeout=60,
        )

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_raises_on_gh_failure(self, mock_gh: MagicMock) -> None:
        mock_gh.side_effect = RuntimeError("gh command failed: not found")
        with pytest.raises(RuntimeError, match="gh command failed"):
            fetch_diff(999)


# ===========================================================================
# fetch_ci_checks
# ===========================================================================


class TestFetchCIChecks:
    """Tests for fetch_ci_checks() with mocked gh CLI."""

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_all_passing_checks(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = GH_CI_CHECKS_JSON
        ci = fetch_ci_checks(39)

        assert isinstance(ci, CIStatus)
        assert ci.all_passed is True
        assert len(ci.checks) == 3

        for check in ci.checks:
            assert check.status == "success"

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_mixed_checks(self, mock_gh: MagicMock) -> None:
        data = [
            {"name": "lint", "state": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "test", "state": "COMPLETED", "conclusion": "FAILURE"},
            {"name": "deploy", "state": "IN_PROGRESS", "conclusion": ""},
        ]
        mock_gh.return_value = json.dumps(data)
        ci = fetch_ci_checks(39)

        assert ci.all_passed is False
        assert len(ci.checks) == 3

        lint = ci.checks[0]
        assert lint.name == "lint"
        assert lint.status == "success"

        test = ci.checks[1]
        assert test.name == "test"
        assert test.status == "failure"

        deploy = ci.checks[2]
        assert deploy.name == "deploy"
        assert deploy.status == "pending"

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_empty_checks_returns_not_passed(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = "[]"
        ci = fetch_ci_checks(39)

        assert ci.all_passed is False
        assert ci.checks == []

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_gh_failure_returns_empty_ci_status(self, mock_gh: MagicMock) -> None:
        """When gh command fails, fetch_ci_checks should return a safe default."""
        mock_gh.side_effect = RuntimeError("gh command failed: not authenticated")
        ci = fetch_ci_checks(39)

        assert ci.all_passed is False
        assert ci.checks == []

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_invalid_json_returns_empty_ci_status(self, mock_gh: MagicMock) -> None:
        """When gh returns invalid JSON, fetch_ci_checks should return a safe default."""
        mock_gh.return_value = "not json at all"
        ci = fetch_ci_checks(39)

        assert ci.all_passed is False
        assert ci.checks == []

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_check_with_unknown_state(self, mock_gh: MagicMock) -> None:
        data = [
            {"name": "custom-check", "state": "QUEUED", "conclusion": ""},
        ]
        mock_gh.return_value = json.dumps(data)
        ci = fetch_ci_checks(39)

        assert len(ci.checks) == 1
        assert ci.checks[0].status == "pending"
        assert ci.all_passed is False

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_check_names_preserved(self, mock_gh: MagicMock) -> None:
        data = [
            {"name": "CI / Build (ubuntu-latest)", "state": "COMPLETED", "conclusion": "SUCCESS"},
        ]
        mock_gh.return_value = json.dumps(data)
        ci = fetch_ci_checks(39)

        assert ci.checks[0].name == "CI / Build (ubuntu-latest)"

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_check_missing_name_defaults_to_unknown(self, mock_gh: MagicMock) -> None:
        data = [
            {"state": "COMPLETED", "conclusion": "SUCCESS"},
        ]
        mock_gh.return_value = json.dumps(data)
        ci = fetch_ci_checks(39)

        assert ci.checks[0].name == "unknown"

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_calls_gh_with_correct_args(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = GH_CI_CHECKS_JSON
        fetch_ci_checks(42)
        mock_gh.assert_called_once_with([
            "pr", "checks", "42",
            "--json", "name,state,conclusion",
        ])

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_single_failing_check_means_not_all_passed(self, mock_gh: MagicMock) -> None:
        data = [
            {"name": "lint", "state": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "test", "state": "COMPLETED", "conclusion": "FAILURE"},
        ]
        mock_gh.return_value = json.dumps(data)
        ci = fetch_ci_checks(39)
        assert ci.all_passed is False

    @patch("pr_review_agent.github.pr_client._run_gh")
    def test_conclusion_is_preserved(self, mock_gh: MagicMock) -> None:
        data = [
            {"name": "lint", "state": "COMPLETED", "conclusion": "SUCCESS"},
        ]
        mock_gh.return_value = json.dumps(data)
        ci = fetch_ci_checks(39)
        assert ci.checks[0].conclusion == "SUCCESS"
