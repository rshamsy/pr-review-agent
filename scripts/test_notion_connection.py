#!/usr/bin/env python3
"""Diagnostic script to test Notion MCP server connection.

Usage:
    python scripts/test_notion_connection.py

Requires NOTION_API_KEY to be set in the environment.
"""

import asyncio
import os
import sys


async def test_connection():
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("ERROR: NOTION_API_KEY is not set")
        sys.exit(1)

    print(f"API key: {api_key[:12]}...{api_key[-4:]}")
    print(f"Python: {sys.version}")

    # Check npx is available
    proc = await asyncio.create_subprocess_exec(
        "npx", "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    print(f"npx version: {stdout.decode().strip()}")

    # Try spawning the MCP server directly to see its stderr
    print("\n--- Spawning Notion MCP server directly ---")
    env = {
        **os.environ,
        "OPENAPI_MCP_HEADERS": f'{{"Authorization": "Bearer {api_key}", "Notion-Version": "2022-06-28"}}',
    }
    proc = await asyncio.create_subprocess_exec(
        "npx", "-y", "@notionhq/notion-mcp-server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    # Give it a few seconds to start up (or crash)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        print(f"Process exited with code: {proc.returncode}")
        if stdout:
            print(f"STDOUT: {stdout.decode()[:500]}")
        if stderr:
            print(f"STDERR: {stderr.decode()[:500]}")
    except asyncio.TimeoutError:
        print("Server started successfully (still running after 15s)")
        proc.terminate()
        await proc.wait()

    # Now try via MCP SDK
    print("\n--- Testing via MCP SDK ---")
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            env=env,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("MCP session initialized successfully!")

                # Try listing tools
                tools = await session.list_tools()
                print(f"Available tools: {[t.name for t in tools.tools]}")

                # Try a simple search
                result = await session.call_tool("API-post-search", {"query": "test"})
                print(f"Search result: {result}")

    except BaseException as exc:
        print(f"MCP connection failed: {type(exc).__name__}: {exc}")
        if isinstance(exc, BaseExceptionGroup):
            for i, sub in enumerate(exc.exceptions):
                print(f"  Sub-exception {i}: {type(sub).__name__}: {sub}")


if __name__ == "__main__":
    asyncio.run(test_connection())
