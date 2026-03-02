"""Notion MCP client — connects to Notion via the MCP Python SDK.

Spawns `npx -y @notionhq/notion-mcp-server` as a child process using StdioClientTransport.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class NotionMCPClient:
    """Async client for Notion via MCP server."""

    def __init__(self, notion_api_key: str | None = None):
        self._api_key = notion_api_key or os.environ.get("NOTION_API_KEY", "")
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
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Notion MCP server: {exc}. "
                "Check that NOTION_API_KEY is valid and npx is working."
            ) from exc

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return the result."""
        if not self._session:
            raise RuntimeError("Not connected. Use 'async with client.connect()' first.")

        result = await self._session.call_tool(name, arguments)
        return result

    async def search_pages(self, query: str) -> list[dict[str, Any]]:
        """Search Notion pages by query text."""
        result = await self._call_tool("notion_search_pages", {"query": query})

        pages: list[dict[str, Any]] = []
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    import json
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
        """Get the full content of a Notion page."""
        result = await self._call_tool(
            "notion_retrieve_page",
            {"page_id": page_id},
        )

        text_parts: list[str] = []
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)

        return "\n".join(text_parts)

    async def get_block_children(self, block_id: str) -> str:
        """Get children blocks of a Notion block."""
        result = await self._call_tool(
            "notion_retrieve_block_children",
            {"block_id": block_id},
        )

        text_parts: list[str] = []
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)

        return "\n".join(text_parts)
