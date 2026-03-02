"""GitHub PR client — wraps gh CLI for PR data retrieval."""

from __future__ import annotations

import json
import subprocess

from pr_review_agent.models.pr import CICheck, CIStatus, FileChange, PRData


def _run_gh(args: list[str], timeout: int = 30) -> str:
    """Run a gh CLI command and return stdout."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh command failed: {result.stderr.strip()}")
    return result.stdout


def fetch_pr(pr_number: int) -> PRData:
    """Fetch PR metadata using gh CLI."""
    raw = _run_gh([
        "pr", "view", str(pr_number),
        "--json", "number,title,author,additions,deletions,files,headRefName",
    ])
    data = json.loads(raw)

    files: list[FileChange] = []
    for f in data.get("files", []):
        files.append(FileChange(
            filename=f.get("path", ""),
            status=_map_file_status(f.get("additions", 0), f.get("deletions", 0)),
            additions=f.get("additions", 0),
            deletions=f.get("deletions", 0),
            patch=None,
        ))

    return PRData(
        number=data["number"],
        title=data["title"],
        author=data.get("author", {}).get("login", "unknown"),
        additions=data.get("additions", 0),
        deletions=data.get("deletions", 0),
        files=files,
        branch=data.get("headRefName", ""),
    )


def _map_file_status(additions: int, deletions: int) -> str:
    """Infer file status from additions/deletions. gh files JSON doesn't always have status."""
    if deletions == 0 and additions > 0:
        return "added"
    if additions == 0 and deletions > 0:
        return "removed"
    return "modified"


def fetch_diff(pr_number: int) -> str:
    """Fetch the full PR diff using gh CLI."""
    return _run_gh(["pr", "diff", str(pr_number)], timeout=60)


def fetch_ci_checks(pr_number: int) -> CIStatus:
    """Fetch CI check status for a PR."""
    try:
        raw = _run_gh([
            "pr", "checks", str(pr_number),
            "--json", "name,state,conclusion",
        ])
        data = json.loads(raw)
    except (RuntimeError, json.JSONDecodeError):
        return CIStatus(all_passed=False, checks=[])

    checks: list[CICheck] = []
    for check in data:
        status = "pending"
        conclusion = check.get("conclusion", "")
        state = check.get("state", "").lower()

        if state == "completed":
            status = "success" if conclusion == "SUCCESS" else "failure"

        checks.append(CICheck(
            name=check.get("name", "unknown"),
            status=status,
            conclusion=conclusion,
        ))

    all_passed = all(c.status == "success" for c in checks) if checks else False
    return CIStatus(all_passed=all_passed, checks=checks)
