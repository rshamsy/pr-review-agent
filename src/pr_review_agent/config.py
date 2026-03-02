"""Environment configuration loader."""

from __future__ import annotations

import shutil
import subprocess

from pydantic import Field
from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    anthropic_api_key: str = ""
    notion_api_key: str = ""
    pr_review_model: str = "claude-sonnet-4-20250514"

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_config() -> AgentConfig:
    """Load configuration from environment variables."""
    return AgentConfig()


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
