"""Notion MCP client — connects to Notion via the MCP Python SDK.

Spawns `npx -y @notionhq/notion-mcp-server` as a child process using StdioClientTransport.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Block types whose content lives under a ``rich_text`` array.
_RICH_TEXT_BLOCK_TYPES = frozenset({
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "toggle",
    "callout",
    "quote",
    "code",
})


def _extract_blocks_from_raw(raw_json: str) -> list[dict[str, Any]]:
    """Parse a block-children JSON string into a list of block dicts.

    Each returned dict has at least ``text``, ``id`` and ``has_children`` keys.
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return []

    results: list[dict[str, Any]] = []
    if isinstance(data, dict) and "results" in data:
        items = data["results"]
    elif isinstance(data, list):
        items = data
    else:
        return []

    for block in items:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")
        block_id = block.get("id", "")
        has_children = block.get("has_children", False)

        text = ""
        if block_type in _RICH_TEXT_BLOCK_TYPES:
            type_data = block.get(block_type, {})
            rich_text_list = type_data.get("rich_text", [])
            text = "".join(
                rt.get("plain_text", "") for rt in rich_text_list if isinstance(rt, dict)
            )

        results.append({
            "text": text,
            "id": block_id,
            "has_children": has_children,
            "type": block_type,
        })

    return results


def _unwrap_exception(exc: BaseException) -> str:
    """Unwrap ExceptionGroup to get the real error message."""
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            return _unwrap_exception(sub)
    return str(exc)


def _unwrap_runtime_error(exc: BaseException) -> RuntimeError | None:
    """If *exc* is an ExceptionGroup hiding a RuntimeError, return it."""
    if isinstance(exc, RuntimeError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _unwrap_runtime_error(sub)
            if found is not None:
                return found
    return None


class NotionMCPClient:
    """Async client for Notion via MCP server."""

    def __init__(self, notion_api_key: str | None = None):
        self._api_key = (notion_api_key or os.environ.get("NOTION_API_KEY", "")).strip().strip("'\"")

        self._session: ClientSession | None = None

    @asynccontextmanager
    async def connect(self) -> AsyncIterator["NotionMCPClient"]:
        """Connect to the Notion MCP server."""
        if not self._api_key:
            raise RuntimeError("NOTION_API_KEY is not set")

        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            env={
                **os.environ,
                "OPENAPI_MCP_HEADERS": f'{{"Authorization": "Bearer {self._api_key}", "Notion-Version": "2022-06-28"}}',
            },
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    try:
                        yield self
                    finally:
                        self._session = None
        except RuntimeError:
            raise
        except BaseException as exc:
            # Async cleanup may wrap our RuntimeError in an ExceptionGroup.
            # Unwrap it so the original clear message propagates.
            inner = _unwrap_runtime_error(exc)
            if inner is not None:
                raise inner from exc
            detail = _unwrap_exception(exc)
            raise RuntimeError(
                f"Failed to connect to Notion MCP server: {detail}. "
                "Check that NOTION_API_KEY is valid and npx is working."
            ) from exc

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return the result."""
        if not self._session:
            raise RuntimeError("Not connected. Use 'async with client.connect()' first.")

        result = await self._session.call_tool(name, arguments)

        # Check if the MCP tool returned an error
        if getattr(result, "isError", False):
            error_text = ""
            if hasattr(result, "content"):
                for block in result.content:
                    if hasattr(block, "text"):
                        error_text = block.text
                        break
            if "401" in error_text or "Unauthorized" in error_text:
                raise RuntimeError(
                    "Notion API returned 401 Unauthorized. "
                    "Check that your NOTION_API_KEY is valid and the integration "
                    "is connected to the relevant pages "
                    "(open page → ··· → Add connections)."
                )
            raise RuntimeError(f"Notion MCP tool error: {error_text}")

        return result

    @staticmethod
    def _check_error_text(text: str) -> None:
        """Raise RuntimeError if *text* looks like a Notion API error."""
        if "401" in text and ("Unauthorized" in text or "unauthorized" in text):
            raise RuntimeError(
                "Notion API returned 401 Unauthorized. "
                "Check that your NOTION_API_KEY is valid and the integration "
                "is connected to the relevant pages "
                "(open page → ··· → Add connections)."
            )
        # Catch other HTTP errors surfaced by the MCP server
        if text.lstrip().startswith("Error") or "status: 4" in text or "status: 5" in text:
            raise RuntimeError(f"Notion API error: {text[:300]}")

    async def search_pages(self, query: str) -> list[dict[str, Any]]:
        """Search Notion pages by query text."""
        result = await self._call_tool("API-post-search", {"query": query})

        pages: list[dict[str, Any]] = []
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    # Detect error responses that weren't flagged via isError
                    self._check_error_text(block.text)
                    try:
                        data = json.loads(block.text)
                        if isinstance(data, list):
                            pages.extend(data)
                        elif isinstance(data, dict):
                            # Could be a single result or a wrapper
                            if "results" in data:
                                pages.extend(data["results"])
                            else:
                                pages.append(data)
                    except json.JSONDecodeError:
                        # Raw text result — wrap it
                        pages.append({"content": block.text})

        return pages

    async def get_page_content(self, page_id: str) -> str:
        """Get the full readable content of a Notion page.

        Fetches block children recursively (the page body), not just the
        page metadata returned by ``API-retrieve-a-page``.
        """
        return await self._get_blocks_recursive(page_id)

    async def get_block_children(self, block_id: str) -> str:
        """Get children blocks of a Notion block (raw MCP text)."""
        result = await self._call_tool(
            "API-get-block-children",
            {"block_id": block_id},
        )

        text_parts: list[str] = []
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    self._check_error_text(block.text)
                    text_parts.append(block.text)

        return "\n".join(text_parts)

    async def _get_blocks_recursive(
        self,
        block_id: str,
        depth: int = 0,
        max_depth: int = 3,
    ) -> str:
        """Recursively fetch block children and return readable text.

        Blocks with ``has_children=True`` are expanded up to *max_depth*
        levels.  Each nesting level adds two-space indentation.
        """
        raw = await self.get_block_children(block_id)
        parsed = _extract_blocks_from_raw(raw)

        indent = "  " * depth
        lines: list[str] = []
        for block in parsed:
            text = block["text"]
            if text:
                lines.append(f"{indent}{text}")

            if block["has_children"] and block["id"] and depth < max_depth:
                nested = await self._get_blocks_recursive(
                    block["id"], depth + 1, max_depth
                )
                if nested:
                    lines.append(nested)

        return "\n".join(lines)
