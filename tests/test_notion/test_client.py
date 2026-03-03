"""Tests for pr_review_agent.notion.client — NotionMCPClient.

Mocks the MCP session to avoid needing a real Notion server.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pr_review_agent.notion.client import NotionMCPClient, _extract_blocks_from_raw


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
            "API-post-search",
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
    """Tests for NotionMCPClient.get_page_content().

    get_page_content now delegates to _get_blocks_recursive which calls
    get_block_children (API-get-block-children), NOT API-retrieve-a-page.
    """

    @pytest.mark.asyncio
    async def test_get_page_content_calls_block_children(self):
        """get_page_content fetches block children, not page metadata."""
        client = NotionMCPClient(notion_api_key="test-key")

        blocks_json = json.dumps({"results": [
            {"id": "b1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": [{"plain_text": "Hello world"}]}},
        ]})

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result([blocks_json])
        client._session = mock_session

        result = await client.get_page_content("page-id-123")

        mock_session.call_tool.assert_awaited_once_with(
            "API-get-block-children",
            {"block_id": "page-id-123"},
        )
        assert "Hello world" in result

    @pytest.mark.asyncio
    async def test_get_page_content_extracts_readable_text(self):
        """Headings and paragraphs are extracted as readable text."""
        client = NotionMCPClient(notion_api_key="test-key")

        blocks_json = json.dumps({"results": [
            {"id": "b1", "type": "heading_1", "has_children": False,
             "heading_1": {"rich_text": [{"plain_text": "Description"}]}},
            {"id": "b2", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": [{"plain_text": "Create a user flow."}]}},
        ]})

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result([blocks_json])
        client._session = mock_session

        result = await client.get_page_content("page-id-123")

        assert "Description" in result
        assert "Create a user flow." in result

    @pytest.mark.asyncio
    async def test_get_page_content_empty_result(self):
        """When MCP returns no blocks, empty string is returned."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result([
            json.dumps({"results": []})
        ])
        client._session = mock_session

        result = await client.get_page_content("page-id-123")

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_page_content_recursive_children(self):
        """Blocks with has_children=True trigger nested fetches."""
        client = NotionMCPClient(notion_api_key="test-key")

        # First call: top-level blocks for the page
        top_level = json.dumps({"results": [
            {"id": "toggle-1", "type": "toggle", "has_children": True,
             "toggle": {"rich_text": [{"plain_text": "Acceptance Criteria"}]}},
        ]})
        # Second call: children of toggle-1
        nested = json.dumps({"results": [
            {"id": "n1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": [{"plain_text": "Must verify email."}]}},
        ]})

        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = [
            _make_mcp_result([top_level]),
            _make_mcp_result([nested]),
        ]
        client._session = mock_session

        result = await client.get_page_content("page-id-123")

        assert "Acceptance Criteria" in result
        assert "Must verify email." in result
        assert mock_session.call_tool.await_count == 2


# ---------------------------------------------------------------------------
# Tests for get_block_children
# ---------------------------------------------------------------------------

class TestGetBlockChildren:
    """Tests for NotionMCPClient.get_block_children()."""

    @pytest.mark.asyncio
    async def test_get_block_children_calls_correct_tool(self):
        """get_block_children should invoke 'API-get-block-children'."""
        client = NotionMCPClient(notion_api_key="test-key")

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_mcp_result(["Block content"])
        client._session = mock_session

        await client.get_block_children("block-id-456")

        mock_session.call_tool.assert_awaited_once_with(
            "API-get-block-children",
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
# Tests for _extract_blocks_from_raw
# ---------------------------------------------------------------------------

class TestExtractBlocksFromRaw:
    """Tests for the _extract_blocks_from_raw helper."""

    def test_paragraph_block(self):
        raw = json.dumps({"results": [
            {"id": "b1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": [{"plain_text": "Hello"}]}},
        ]})
        blocks = _extract_blocks_from_raw(raw)
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Hello"
        assert blocks[0]["has_children"] is False

    def test_heading_blocks(self):
        raw = json.dumps({"results": [
            {"id": "h1", "type": "heading_1", "has_children": False,
             "heading_1": {"rich_text": [{"plain_text": "Title"}]}},
            {"id": "h2", "type": "heading_2", "has_children": False,
             "heading_2": {"rich_text": [{"plain_text": "Subtitle"}]}},
        ]})
        blocks = _extract_blocks_from_raw(raw)
        assert blocks[0]["text"] == "Title"
        assert blocks[1]["text"] == "Subtitle"

    def test_list_items(self):
        raw = json.dumps({"results": [
            {"id": "li1", "type": "bulleted_list_item", "has_children": False,
             "bulleted_list_item": {"rich_text": [{"plain_text": "Bullet one"}]}},
            {"id": "li2", "type": "numbered_list_item", "has_children": False,
             "numbered_list_item": {"rich_text": [{"plain_text": "Number one"}]}},
        ]})
        blocks = _extract_blocks_from_raw(raw)
        assert blocks[0]["text"] == "Bullet one"
        assert blocks[1]["text"] == "Number one"

    def test_multiple_rich_text_segments(self):
        """rich_text with multiple segments are concatenated."""
        raw = json.dumps({"results": [
            {"id": "b1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": [
                 {"plain_text": "Hello "},
                 {"plain_text": "world"},
             ]}},
        ]})
        blocks = _extract_blocks_from_raw(raw)
        assert blocks[0]["text"] == "Hello world"

    def test_empty_rich_text(self):
        raw = json.dumps({"results": [
            {"id": "b1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": []}},
        ]})
        blocks = _extract_blocks_from_raw(raw)
        assert blocks[0]["text"] == ""

    def test_unknown_block_type(self):
        """Unknown block types produce empty text but are still returned."""
        raw = json.dumps({"results": [
            {"id": "b1", "type": "divider", "has_children": False},
        ]})
        blocks = _extract_blocks_from_raw(raw)
        assert len(blocks) == 1
        assert blocks[0]["text"] == ""

    def test_has_children_true(self):
        raw = json.dumps({"results": [
            {"id": "t1", "type": "toggle", "has_children": True,
             "toggle": {"rich_text": [{"plain_text": "Expand me"}]}},
        ]})
        blocks = _extract_blocks_from_raw(raw)
        assert blocks[0]["has_children"] is True
        assert blocks[0]["id"] == "t1"

    def test_invalid_json(self):
        assert _extract_blocks_from_raw("not json") == []

    def test_empty_results(self):
        assert _extract_blocks_from_raw(json.dumps({"results": []})) == []

    def test_list_format(self):
        """Handles raw list format (no 'results' wrapper)."""
        raw = json.dumps([
            {"id": "b1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": [{"plain_text": "Direct list"}]}},
        ])
        blocks = _extract_blocks_from_raw(raw)
        assert blocks[0]["text"] == "Direct list"


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


# ---------------------------------------------------------------------------
# Tests for connect() error handling
# ---------------------------------------------------------------------------

class TestConnect:
    """Tests for NotionMCPClient.connect() error handling."""

    @pytest.mark.asyncio
    async def test_connect_raises_when_no_api_key(self):
        """connect() raises RuntimeError when API key is empty."""
        client = NotionMCPClient(notion_api_key="")

        with pytest.raises(RuntimeError, match="NOTION_API_KEY is not set"):
            async with client.connect():
                pass

    @pytest.mark.asyncio
    async def test_connect_raises_when_api_key_none(self):
        """connect() raises RuntimeError when API key resolves to empty."""
        with patch.dict("os.environ", {}, clear=True):
            client = NotionMCPClient(notion_api_key=None)

            with pytest.raises(RuntimeError, match="NOTION_API_KEY is not set"):
                async with client.connect():
                    pass

    @pytest.mark.asyncio
    async def test_connect_wraps_server_startup_failure(self):
        """connect() wraps server startup exceptions in RuntimeError."""
        client = NotionMCPClient(notion_api_key="valid-key")

        with patch("pr_review_agent.notion.client.stdio_client") as mock_stdio:
            mock_stdio.side_effect = OSError("npx not found")

            with pytest.raises(RuntimeError, match="Failed to connect to Notion MCP server"):
                async with client.connect():
                    pass

    @pytest.mark.asyncio
    async def test_connect_preserves_runtime_errors(self):
        """connect() re-raises RuntimeError directly (does not double-wrap)."""
        client = NotionMCPClient(notion_api_key="valid-key")

        with patch("pr_review_agent.notion.client.stdio_client") as mock_stdio:
            mock_stdio.side_effect = RuntimeError("custom runtime error")

            with pytest.raises(RuntimeError, match="custom runtime error"):
                async with client.connect():
                    pass
