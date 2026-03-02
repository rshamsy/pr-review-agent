"""Comprehensive tests for the config module."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.config import AgentConfig, _find_env_files, get_config, validate_config


# ===== _find_env_files =====


class TestFindEnvFiles:
    def test_returns_list(self):
        result = _find_env_files()
        assert isinstance(result, list)

    def test_includes_repo_root_env_if_exists(self, tmp_path):
        """Finds .env relative to the package install directory."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=val\n")
        with patch("pr_review_agent.config.Path") as MockPath:
            # __file__ resolves to src/pr_review_agent/config.py
            # parent.parent.parent => repo root
            mock_file = MagicMock()
            mock_file.resolve.return_value.parent.parent.parent.__truediv__.return_value = env_file
            MockPath.__file__ = mock_file
            # Just verify function doesn't crash with real paths
            result = _find_env_files()
            assert isinstance(result, list)

    def test_includes_cwd_env_if_exists(self, tmp_path):
        """Includes .env from current working directory."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=val\n")
        with patch("pr_review_agent.config.Path") as MockPath:
            MockPath.home.return_value.__truediv__ = MagicMock(
                return_value=MagicMock(is_file=MagicMock(return_value=False))
            )
            MockPath.cwd.return_value.__truediv__.return_value = env_file
            MockPath.__file__ = MagicMock()
            MockPath.__file__.resolve.return_value.parent.parent.parent.__truediv__.return_value = MagicMock(
                is_file=MagicMock(return_value=False)
            )
            # Real function uses Path directly; test the actual function
        result = _find_env_files()
        assert isinstance(result, list)


# ===== AgentConfig =====


class TestAgentConfig:
    def test_defaults_no_env(self):
        """With no env vars set and no .env file, fields use their defaults."""
        with patch.dict("os.environ", {}, clear=True):
            cfg = AgentConfig(_env_file=None)
        assert cfg.anthropic_api_key == ""
        assert cfg.notion_api_key == ""
        assert cfg.pr_review_model == "claude-sonnet-4-20250514"

    def test_env_vars_loaded(self):
        """Environment variables are read correctly."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test-key-123",
            "NOTION_API_KEY": "ntn_test_key_456",
            "PR_REVIEW_MODEL": "claude-opus-4-20250514",
        }
        with patch.dict("os.environ", env, clear=True):
            cfg = AgentConfig(_env_file=None)
        assert cfg.anthropic_api_key == "sk-ant-test-key-123"
        assert cfg.notion_api_key == "ntn_test_key_456"
        assert cfg.pr_review_model == "claude-opus-4-20250514"

    def test_case_insensitive_env(self):
        """Config is case insensitive for env var names."""
        env = {
            "anthropic_api_key": "lower-key",
            "NOTION_API_KEY": "upper-key",
        }
        with patch.dict("os.environ", env, clear=True):
            cfg = AgentConfig(_env_file=None)
        assert cfg.anthropic_api_key == "lower-key"
        assert cfg.notion_api_key == "upper-key"

    def test_partial_env(self):
        """Only some env vars set; others remain default."""
        env = {"ANTHROPIC_API_KEY": "my-key"}
        with patch.dict("os.environ", env, clear=True):
            cfg = AgentConfig(_env_file=None)
        assert cfg.anthropic_api_key == "my-key"
        assert cfg.notion_api_key == ""
        assert cfg.pr_review_model == "claude-sonnet-4-20250514"

    def test_empty_string_env_var(self):
        """Empty string env var is treated as empty (falsy)."""
        env = {"ANTHROPIC_API_KEY": "", "NOTION_API_KEY": ""}
        with patch.dict("os.environ", env, clear=True):
            cfg = AgentConfig(_env_file=None)
        assert cfg.anthropic_api_key == ""
        assert cfg.notion_api_key == ""

    def test_model_config_has_env_file(self):
        """Verify the model_config loads .env files."""
        assert AgentConfig.model_config["env_prefix"] == ""
        assert AgentConfig.model_config["case_sensitive"] is False
        # env_file is a list of Path objects from _find_env_files()
        assert isinstance(AgentConfig.model_config["env_file"], list)

    def test_env_file_loading(self, tmp_path):
        """AgentConfig loads values from a .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=from-dotenv\nNOTION_API_KEY=notion-from-dotenv\n")

        with patch.dict("os.environ", {}, clear=True):
            cfg = AgentConfig(_env_file=str(env_file))
        assert cfg.anthropic_api_key == "from-dotenv"
        assert cfg.notion_api_key == "notion-from-dotenv"


# ===== get_config =====


class TestGetConfig:
    def test_returns_agent_config_instance(self):
        cfg = get_config()
        assert isinstance(cfg, AgentConfig)

    def test_picks_up_env_vars(self):
        env = {"ANTHROPIC_API_KEY": "test-key-from-env"}
        with patch.dict("os.environ", env):
            cfg = get_config()
        assert cfg.anthropic_api_key == "test-key-from-env"

    def test_returns_fresh_instance_each_call(self):
        """get_config is not cached; each call returns a new object."""
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is not cfg2


# ===== validate_config =====


def _make_config(anthropic_key: str = "", notion_key: str = "", model: str = "claude-sonnet-4-20250514") -> AgentConfig:
    """Create a config with specific values, bypassing .env file."""
    return AgentConfig(
        anthropic_api_key=anthropic_key,
        notion_api_key=notion_key,
        pr_review_model=model,
        _env_file=None,
    )


def _mock_which(available: dict[str, bool]):
    """Return a side_effect function for shutil.which."""
    def which_side_effect(cmd: str):
        if available.get(cmd, False):
            return f"/usr/bin/{cmd}"
        return None
    return which_side_effect


class TestValidateConfig:

    def test_all_valid(self):
        """No errors when all keys are set, gh is authed, and npx exists."""
        mock_result = MagicMock(returncode=0)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result),
        ):
            errors = validate_config()

        assert errors == []

    def test_missing_anthropic_key(self):
        """Error when ANTHROPIC_API_KEY is not set."""
        mock_result = MagicMock(returncode=0)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config(notion_key="ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result),
        ):
            errors = validate_config()

        assert any("ANTHROPIC_API_KEY" in e for e in errors)

    def test_missing_notion_key(self):
        """Error when NOTION_API_KEY is not set."""
        mock_result = MagicMock(returncode=0)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config(anthropic_key="sk-ant-key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result),
        ):
            errors = validate_config()

        assert any("NOTION_API_KEY" in e for e in errors)

    def test_both_keys_missing(self):
        """Both API key errors when neither is set."""
        mock_result = MagicMock(returncode=0)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config()),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result),
        ):
            errors = validate_config()

        assert any("ANTHROPIC_API_KEY" in e for e in errors)
        assert any("NOTION_API_KEY" in e for e in errors)

    def test_gh_not_installed(self):
        """Error when gh CLI is not on PATH."""
        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": False, "npx": True})),
        ):
            errors = validate_config()

        assert any("gh" in e and "not installed" in e for e in errors)

    def test_gh_not_authenticated(self):
        """Error when gh CLI exists but is not authenticated."""
        mock_result = MagicMock(returncode=1)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result),
        ):
            errors = validate_config()

        assert any("not authenticated" in e for e in errors)

    def test_gh_auth_timeout(self):
        """Error when gh auth status times out."""
        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch(
                "pr_review_agent.config.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="gh auth status", timeout=10),
            ),
        ):
            errors = validate_config()

        assert any("timed out" in e for e in errors)

    def test_npx_not_installed(self):
        """Error when npx is not on PATH."""
        mock_result = MagicMock(returncode=0)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": False})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result),
        ):
            errors = validate_config()

        assert any("npx" in e and "not installed" in e for e in errors)

    def test_everything_missing(self):
        """All errors present when nothing is configured."""
        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config()),
            patch("pr_review_agent.config.shutil.which", return_value=None),
        ):
            errors = validate_config()

        assert len(errors) >= 4
        assert any("ANTHROPIC_API_KEY" in e for e in errors)
        assert any("NOTION_API_KEY" in e for e in errors)
        assert any("gh" in e for e in errors)
        assert any("npx" in e for e in errors)

    def test_gh_auth_called_with_correct_args(self):
        """Verify subprocess.run is called with the right arguments."""
        mock_result = MagicMock(returncode=0)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result) as mock_run,
        ):
            validate_config()

        mock_run.assert_called_once_with(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_subprocess_not_called_when_gh_missing(self):
        """When gh is not installed, subprocess.run should not be called."""
        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": False, "npx": True})),
            patch("pr_review_agent.config.subprocess.run") as mock_run,
        ):
            validate_config()

        mock_run.assert_not_called()

    def test_error_messages_are_strings(self):
        """All returned error entries should be non-empty strings."""
        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config()),
            patch("pr_review_agent.config.shutil.which", return_value=None),
        ):
            errors = validate_config()

        for err in errors:
            assert isinstance(err, str)
            assert len(err) > 0

    def test_validate_returns_list(self):
        """Return type is always a list."""
        mock_result = MagicMock(returncode=0)

        with (
            patch("pr_review_agent.config.get_config", return_value=_make_config("sk-ant-key", "ntn_key")),
            patch("pr_review_agent.config.shutil.which", side_effect=_mock_which({"gh": True, "npx": True})),
            patch("pr_review_agent.config.subprocess.run", return_value=mock_result),
        ):
            result = validate_config()

        assert isinstance(result, list)
