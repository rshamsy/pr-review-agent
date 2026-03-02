"""Tests for pr_review_agent.notion.search — contextual search and helper functions.

Mocks NotionMCPClient to avoid real Notion connections.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pr_review_agent.models.notion import NotionSearchResult
from pr_review_agent.notion.search import (
    _extract_page_id,
    _extract_title,
    _extract_url,
    _page_id_from_url,
    contextual_search,
    fetch_page_by_url,
)


# ===========================================================================
# Tests for _extract_page_id
# ===========================================================================

class TestExtractPageId:
    """Tests for the _extract_page_id helper."""

    def test_extracts_id_from_id_key(self):
        assert _extract_page_id({"id": "abc-123"}) == "abc-123"

    def test_extracts_id_from_page_id_key(self):
        assert _extract_page_id({"page_id": "def-456"}) == "def-456"

    def test_prefers_id_over_page_id(self):
        assert _extract_page_id({"id": "abc", "page_id": "def"}) == "abc"

    def test_returns_empty_string_when_missing(self):
        assert _extract_page_id({}) == ""
        assert _extract_page_id({"title": "no id here"}) == ""


# ===========================================================================
# Tests for _extract_title
# ===========================================================================

class TestExtractTitle:
    """Tests for the _extract_title helper."""

    def test_extracts_from_properties_name_title_list(self):
        """Standard Notion response format: properties.Name.title[].plain_text."""
        item = {
            "properties": {
                "Name": {
                    "title": [{"plain_text": "My Page Title"}]
                }
            }
        }
        assert _extract_title(item) == "My Page Title"

    def test_extracts_from_properties_title_key(self):
        """Alternative key: properties.Title.title[].plain_text."""
        item = {
            "properties": {
                "Title": {
                    "title": [{"plain_text": "Another Title"}]
                }
            }
        }
        assert _extract_title(item) == "Another Title"

    def test_extracts_from_properties_string_value(self):
        """When property value is a plain string."""
        item = {
            "properties": {
                "Name": "Direct String Title"
            }
        }
        assert _extract_title(item) == "Direct String Title"

    def test_fallback_to_title_key(self):
        """Falls back to top-level 'title' key."""
        item = {"title": "Top Level Title"}
        assert _extract_title(item) == "Top Level Title"

    def test_fallback_to_name_key(self):
        """Falls back to top-level 'name' key."""
        item = {"name": "Named Item"}
        assert _extract_title(item) == "Named Item"

    def test_returns_untitled_when_nothing_found(self):
        assert _extract_title({}) == "Untitled"

    def test_handles_empty_title_list(self):
        """When properties.Name.title is an empty list."""
        item = {
            "properties": {
                "Name": {"title": []}
            }
        }
        # Falls through to the fallback
        assert _extract_title(item) == "Untitled"

    def test_handles_properties_with_lowercase_name(self):
        """properties.name (lowercase) should also be checked."""
        item = {
            "properties": {
                "name": "lowercase name"
            }
        }
        assert _extract_title(item) == "lowercase name"


# ===========================================================================
# Tests for _extract_url
# ===========================================================================

class TestExtractUrl:
    """Tests for the _extract_url helper."""

    def test_extracts_url(self):
        assert _extract_url({"url": "https://notion.so/page"}) == "https://notion.so/page"

    def test_extracts_public_url(self):
        assert _extract_url({"public_url": "https://notion.so/public"}) == "https://notion.so/public"

    def test_prefers_url_over_public_url(self):
        item = {
            "url": "https://notion.so/private",
            "public_url": "https://notion.so/public",
        }
        assert _extract_url(item) == "https://notion.so/private"

    def test_returns_empty_string_when_missing(self):
        assert _extract_url({}) == ""


# ===========================================================================
# Tests for _page_id_from_url
# ===========================================================================

class TestPageIdFromUrl:
    """Tests for the _page_id_from_url helper."""

    def test_extracts_id_from_standard_notion_url(self):
        """Standard Notion URL with slug and 32-char hex ID at the end."""
        url = "https://www.notion.so/workspace/Payment-Tracking-abc123def45678901234567890abcdef"
        result = _page_id_from_url(url)
        # The last 32 hex chars extracted from the slug
        assert len(result) == 36  # UUID format: 8-4-4-4-12
        assert "-" in result

    def test_extracts_id_from_url_with_query_params(self):
        """Query params are stripped before extraction."""
        url = "https://www.notion.so/workspace/Page-abc123def45678901234567890abcdef?v=123"
        result = _page_id_from_url(url)
        assert len(result) == 36

    def test_extracts_id_from_plain_id_url(self):
        """URL where the last segment is just a 32-char hex ID."""
        url = "https://www.notion.so/abc123def45678901234567890abcdef"
        result = _page_id_from_url(url)
        assert len(result) == 36

    def test_formats_as_uuid(self):
        """Result should be formatted as UUID: 8-4-4-4-12."""
        url = "https://www.notion.so/workspace/Page-00112233445566778899aabbccddeeff"
        result = _page_id_from_url(url)
        parts = result.split("-")
        assert len(parts) == 5
        assert [len(p) for p in parts] == [8, 4, 4, 4, 12]

    def test_returns_segment_when_not_enough_hex_chars(self):
        """When less than 32 hex chars, returns the last segment as-is."""
        url = "https://www.notion.so/short"
        result = _page_id_from_url(url)
        assert result == "short"

    def test_handles_trailing_slash(self):
        """Trailing slash is stripped."""
        url = "https://www.notion.so/workspace/Page-00112233445566778899aabbccddeeff/"
        result = _page_id_from_url(url)
        assert len(result) == 36

    def test_handles_hyphenated_id_in_url(self):
        """IDs with hyphens inside the URL path."""
        # The function strips non-hex chars, so hyphens in the ID are handled
        url = "https://www.notion.so/00112233-4455-6677-8899-aabbccddeeff"
        result = _page_id_from_url(url)
        assert len(result) == 36


# ===========================================================================
# Tests for contextual_search
# ===========================================================================

class TestContextualSearch:
    """Tests for contextual_search() with mocked NotionMCPClient."""

    @pytest.mark.asyncio
    async def test_returns_notion_search_results(self):
        """contextual_search returns a list of NotionSearchResult."""
        mock_client = AsyncMock()
        mock_client.search_pages.return_value = [
            {"id": "page-1", "title": "Payment Feature", "url": "https://notion.so/page-1"},
            {"id": "page-2", "title": "Export Feature", "url": "https://notion.so/page-2"},
        ]
        mock_client.get_page_content.return_value = "Page content here"

        results = await contextual_search(mock_client, "Add payment tracking")

        assert len(results) == 2
        assert all(isinstance(r, NotionSearchResult) for r in results)
        assert results[0].page_id == "page-1"
        assert results[0].title == "Payment Feature"
        assert results[0].content == "Page content here"

    @pytest.mark.asyncio
    async def test_uses_pr_summary_as_query(self):
        """The PR summary is passed directly as the search query."""
        mock_client = AsyncMock()
        mock_client.search_pages.return_value = []

        await contextual_search(mock_client, "my pr summary text")

        mock_client.search_pages.assert_awaited_once_with("my pr summary text")

    @pytest.mark.asyncio
    async def test_fetches_page_content_for_each_result(self):
        """get_page_content is called for each result with a valid page_id."""
        mock_client = AsyncMock()
        mock_client.search_pages.return_value = [
            {"id": "p1", "title": "A"},
            {"id": "p2", "title": "B"},
        ]
        mock_client.get_page_content.return_value = "content"

        await contextual_search(mock_client, "test")

        assert mock_client.get_page_content.await_count == 2

    @pytest.mark.asyncio
    async def test_handles_content_fetch_failure(self):
        """When get_page_content fails, falls back to item content."""
        mock_client = AsyncMock()
        mock_client.search_pages.return_value = [
            {"id": "p1", "title": "A", "content": "fallback text"},
        ]
        mock_client.get_page_content.side_effect = Exception("MCP error")

        results = await contextual_search(mock_client, "test")

        assert len(results) == 1
        assert results[0].content == "fallback text"

    @pytest.mark.asyncio
    async def test_respects_max_results(self):
        """Only max_results pages are processed."""
        mock_client = AsyncMock()
        mock_client.search_pages.return_value = [
            {"id": f"p{i}", "title": f"Page {i}"} for i in range(10)
        ]
        mock_client.get_page_content.return_value = "content"

        results = await contextual_search(mock_client, "test", max_results=3)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_search_results(self):
        """Returns empty list when search finds nothing."""
        mock_client = AsyncMock()
        mock_client.search_pages.return_value = []

        results = await contextual_search(mock_client, "test")

        assert results == []

    @pytest.mark.asyncio
    async def test_skips_content_fetch_for_empty_page_id(self):
        """When page_id is empty, get_page_content is not called."""
        mock_client = AsyncMock()
        mock_client.search_pages.return_value = [
            {"title": "No ID Page"},  # no 'id' or 'page_id'
        ]

        results = await contextual_search(mock_client, "test")

        assert len(results) == 1
        assert results[0].page_id == ""
        mock_client.get_page_content.assert_not_awaited()


# ===========================================================================
# Tests for fetch_page_by_url
# ===========================================================================

class TestFetchPageByUrl:
    """Tests for fetch_page_by_url() with mocked NotionMCPClient."""

    @pytest.mark.asyncio
    async def test_returns_notion_search_result(self):
        """fetch_page_by_url returns a NotionSearchResult."""
        mock_client = AsyncMock()
        mock_client.get_page_content.return_value = "Full page content"

        url = "https://www.notion.so/workspace/My-Page-00112233445566778899aabbccddeeff"
        result = await fetch_page_by_url(mock_client, url)

        assert isinstance(result, NotionSearchResult)
        assert result.url == url
        assert result.content == "Full page content"

    @pytest.mark.asyncio
    async def test_extracts_page_id_from_url(self):
        """The page ID is extracted from the URL and used to fetch content."""
        mock_client = AsyncMock()
        mock_client.get_page_content.return_value = "content"

        url = "https://www.notion.so/workspace/Page-00112233445566778899aabbccddeeff"
        result = await fetch_page_by_url(mock_client, url)

        # Verify the page_id was extracted and formatted as UUID
        assert len(result.page_id) == 36
        # Verify get_page_content was called with the extracted ID
        mock_client.get_page_content.assert_awaited_once_with(result.page_id)

    @pytest.mark.asyncio
    async def test_title_is_derived_from_page_id(self):
        """Title is set as 'Page <first 8 chars>...'."""
        mock_client = AsyncMock()
        mock_client.get_page_content.return_value = "content"

        url = "https://www.notion.so/workspace/Page-00112233445566778899aabbccddeeff"
        result = await fetch_page_by_url(mock_client, url)

        assert result.title.startswith("Page ")
        assert result.title.endswith("...")
