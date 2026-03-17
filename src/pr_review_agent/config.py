"""Environment configuration loader."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from pydantic_settings import BaseSettings

KNOWN_ENV_VARS: frozenset[str] = frozenset({
    "ANTHROPIC_API_KEY",
    "NOTION_API_KEY",
    "NOTION_CONTEXT_PAGES",
    "PR_REVIEW_MODEL",
    "TEST_VERIFICATION_MODE",
    "TEST_VERIFICATION_MODEL",
})

USER_ENV_FILE: Path = Path.home() / ".config" / "pr-review-agent" / ".env"


def update_user_env(key: str, value: str) -> Path:
    """Write *key=value* to the user-level .env file.

    - Creates ``~/.config/pr-review-agent/`` if it doesn't exist.
    - Replaces an existing line for *key* in-place, or appends a new one.
    - Returns the path that was written to.

    Raises ``ValueError`` if *key* is not in ``KNOWN_ENV_VARS``.
    """
    key = key.upper()
    if key not in KNOWN_ENV_VARS:
        raise ValueError(
            f"Unknown env var: {key}. "
            f"Allowed: {', '.join(sorted(KNOWN_ENV_VARS))}"
        )

    USER_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)

    new_line = f"{key}={value.strip()}"
    if USER_ENV_FILE.exists():
        lines = USER_ENV_FILE.read_text().splitlines()
        replaced = False
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(f"{key}="):
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)
        USER_ENV_FILE.write_text("\n".join(lines) + "\n")
    else:
        USER_ENV_FILE.write_text(new_line + "\n")

    return USER_ENV_FILE


def _find_env_files() -> list[Path]:
    """Return .env file paths to load, in priority order (last wins).

    Searches:
      1. The package install directory (for dev: the repo root .env)
      2. ~/.config/pr-review-agent/.env  (user-level config)
      3. The current working directory .env (project-level override)
    """
    candidates = [
        Path(__file__).resolve().parent.parent.parent / ".env",  # repo root (src/../../../.env)
        Path.home() / ".config" / "pr-review-agent" / ".env",
        Path.cwd() / ".env",
    ]
    return [p for p in candidates if p.is_file()]


class AgentConfig(BaseSettings):
    anthropic_api_key: str = ""
    notion_api_key: str = ""
    notion_context_pages: str = ""
    pr_review_model: str = "claude-sonnet-4-20250514"
    test_verification_mode: str = "default"
    test_verification_model: str = "claude-haiku-4-5-20251001"

    def get_context_page_urls(self) -> list[str]:
        """Split and strip the comma-separated NOTION_CONTEXT_PAGES value."""
        if not self.notion_context_pages:
            return []
        return [u.strip() for u in self.notion_context_pages.split(",") if u.strip()]

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
        "env_file": _find_env_files(),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def get_config() -> AgentConfig:
    """Load configuration from environment variables.

    Also exports key variables to os.environ so that downstream libraries
    (e.g. langchain-anthropic's ChatAnthropic) that read env vars directly
    can find them.
    """
    config = AgentConfig()
    if config.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = config.anthropic_api_key
    if config.notion_api_key and not os.environ.get("NOTION_API_KEY"):
        os.environ["NOTION_API_KEY"] = config.notion_api_key
    return config


def validate_config() -> list[str]:
    """Validate all configuration. Returns list of error messages (empty = all good)."""
    errors: list[str] = []
    config = get_config()

    if not config.anthropic_api_key:
        errors.append("ANTHROPIC_API_KEY is not set")

    if not config.notion_api_key:
        errors.append("NOTION_API_KEY is not set")

    # Check gh CLI
    if not shutil.which("gh"):
        errors.append("GitHub CLI (gh) is not installed. Install from https://cli.github.com/")
    else:
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                errors.append("GitHub CLI (gh) is not authenticated. Run: gh auth login")
        except subprocess.TimeoutExpired:
            errors.append("GitHub CLI (gh) auth check timed out")

    # Check npx
    if not shutil.which("npx"):
        errors.append("npx is not installed. Install Node.js from https://nodejs.org/")

    return errors
