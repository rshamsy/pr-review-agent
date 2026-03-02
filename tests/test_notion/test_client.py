"""Tests for pr_review_agent.notion.client — NotionMCPClient.

Mocks the MCP session to avoid needing a real Notion server.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pr_review_agent.notion.client import NotionMCPClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mcp_result(content_texts: list[str]):
    """Build a fake MCP CallToolResult with `.content` containing text blocks."""
    blocks = [SimpleNamespace(text=t) for t in content_texts]
    return SimpleNamespace(content=blocks)


# ---------------------------------------------------------------------------
# Tests for search_pages
# ---------------------------------------------------------------------------

class TestSearchPages:
    """Tests for NotionMCPClient.search_pages()."""

    @pytest.mark.asyncio
    async def test_search_pages_calls_correct_mcp_tool(self):
        """search_pages should invoke the 'notion_search_pages' MCP tool."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result([
            json.dumps([{"id": "page-1", "title": "Test Page"}])
        ])
        client._session = mock_session

        await client.search_pages("supplier payments")

        mock_session.call_tool.assert_awaited_once_with(
            "notion_search_pages",
            {"query": "supplier payments"},
        )

    @pytest.mark.asyncio
    async def test_search_pages_parses_list_result(self):
        """When MCP returns a JSON list, pages are extracted correctly."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        pages_json = json.dumps([
            {"id": "p1", "title": "Page One"},
            {"id": "p2", "title": "Page Two"},
        ])
        mock_session.call_tool.return_value = _make_mcp_result([pages_json])
        client._session = mock_session

        result = await client.search_pages("test query")

        assert len(result) == 2
        assert result[0]["id"] == "p1"
        assert result[1]["title"] == "Page Two"

    @pytest.mark.asyncio
    async def test_search_pages_parses_dict_with_results_key(self):
        """When MCP returns a dict with 'results' key, pages are extracted."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        wrapper_json = json.dumps({
            "results": [
                {"id": "p1", "title": "Page One"},
            ]
        })
        mock_session.call_tool.return_value = _make_mcp_result([wrapper_json])
        client._session = mock_session

        result = await client.search_pages("test query")

        assert len(result) == 1
        assert result[0]["id"] == "p1"

    @pytest.mark.asyncio
    async def test_search_pages_parses_single_dict(self):
        """When MCP returns a single dict without 'results', it is wrapped."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        single_json = json.dumps({"id": "p1", "title": "Single"})
        mock_session.call_tool.return_value = _make_mcp_result([single_json])
        client._session = mock_session

        result = await client.search_pages("test query")

        assert len(result) == 1
        assert result[0]["id"] == "p1"

    @pytest.mark.asyncio
    async def test_search_pages_handles_invalid_json(self):
        """Non-JSON text blocks are wrapped as {'content': text}."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result(["not valid json"])
        client._session = mock_session

        result = await client.search_pages("test query")

        assert len(result) == 1
        assert result[0]["content"] == "not valid json"

    @pytest.mark.asyncio
    async def test_search_pages_handles_empty_content(self):
        """When MCP returns no content blocks, an empty list is returned."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = SimpleNamespace(content=[])
        client._session = mock_session

        result = await client.search_pages("test query")

        assert result == []

    @pytest.mark.asyncio
    async def test_search_pages_raises_when_not_connected(self):
        """Calling search_pages without a session raises RuntimeError."""
        client = NotionMCPClient(notion_api_key="test-key")
        # client._session is None by default

        with pytest.raises(RuntimeError, match="Not connected"):
            await client.search_pages("test query")


# ---------------------------------------------------------------------------
# Tests for get_page_content
# ---------------------------------------------------------------------------

class TestGetPageContent:
    """Tests for NotionMCPClient.get_page_content()."""

    @pytest.mark.asyncio
    async def test_get_page_content_calls_correct_tool(self):
        """get_page_content should invoke 'notion_retrieve_page'."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result(["Page content here"])
        client._session = mock_session

        await client.get_page_content("page-id-123")

        mock_session.call_tool.assert_awaited_once_with(
            "notion_retrieve_page",
            {"page_id": "page-id-123"},
        )

    @pytest.mark.asyncio
    async def test_get_page_content_joins_text_blocks(self):
        """Multiple text blocks are joined with newlines."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result([
            "First paragraph",
            "Second paragraph",
        ])
        client._session = mock_session

        result = await client.get_page_content("page-id-123")

        assert result == "First paragraph\nSecond paragraph"

    @pytest.mark.asyncio
    async def test_get_page_content_empty_result(self):
        """When MCP returns no content blocks, empty string is returned."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = SimpleNamespace(content=[])
        client._session = mock_session

        result = await client.get_page_content("page-id-123")

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_page_content_no_content_attr(self):
        """When MCP result has no content attr, empty string is returned."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = SimpleNamespace()
        client._session = mock_session

        result = await client.get_page_content("page-id-123")

        assert result == ""


# ---------------------------------------------------------------------------
# Tests for get_block_children
# ---------------------------------------------------------------------------

class TestGetBlockChildren:
    """Tests for NotionMCPClient.get_block_children()."""

    @pytest.mark.asyncio
    async def test_get_block_children_calls_correct_tool(self):
        """get_block_children should invoke 'notion_retrieve_block_children'."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result(["Block content"])
        client._session = mock_session

        await client.get_block_children("block-id-456")

        mock_session.call_tool.assert_awaited_once_with(
            "notion_retrieve_block_children",
            {"block_id": "block-id-456"},
        )

    @pytest.mark.asyncio
    async def test_get_block_children_returns_joined_text(self):
        """Block children text parts are joined with newlines."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result([
            "Child block 1",
            "Child block 2",
        ])
        client._session = mock_session

        result = await client.get_block_children("block-id-456")

        assert result == "Child block 1\nChild block 2"


# ---------------------------------------------------------------------------
# Tests for _call_tool
# ---------------------------------------------------------------------------

class TestCallTool:
    """Tests for the internal _call_tool method."""

    @pytest.mark.asyncio
    async def test_call_tool_raises_when_no_session(self):
        """_call_tool raises RuntimeError when not connected."""
        client = NotionMCPClient(notion_api_key="test-key")

        with pytest.raises(RuntimeError, match="Not connected"):
            await client._call_tool("some_tool", {"key": "value"})

    @pytest.mark.asyncio
    async def test_call_tool_returns_session_result(self):
        """_call_tool returns the raw result from session.call_tool."""
        client = NotionMCPClient(notion_api_key="test-key")

        expected = SimpleNamespace(content=[])
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = expected
        client._session = mock_session

        result = await client._call_tool("some_tool", {"key": "value"})

        assert result is expected


# ---------------------------------------------------------------------------
# Tests for __init__
# ---------------------------------------------------------------------------

class TestInit:
    """Tests for NotionMCPClient initialization."""

    def test_init_with_explicit_key(self):
        """API key is stored when provided explicitly."""
        client = NotionMCPClient(notion_api_key="my-secret-key")
        assert client._api_key == "my-secret-key"

    @patch.dict("os.environ", {"NOTION_API_KEY": "env-key"})
    def test_init_falls_back_to_env(self):
        """API key falls back to NOTION_API_KEY env var."""
        client = NotionMCPClient()
        assert client._api_key == "env-key"

    @patch.dict("os.environ", {}, clear=True)
    def test_init_default_empty_string(self):
        """API key defaults to empty string when not set."""
        client = NotionMCPClient()
        assert client._api_key == ""
