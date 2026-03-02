"""Post review comments to GitHub PRs."""

from __future__ import annotations

import subprocess
import tempfile


def post_pr_comment(pr_number: int, markdown_body: str) -> None:
    """Post a markdown comment to a GitHub PR using gh CLI."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(markdown_body)
        f.flush()

        result = subprocess.run(
            ["gh", "pr", "comment", str(pr_number), "--body-file", f.name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to post comment: {result.stderr.strip()}")
