"""Diagnostic script to test Notion MCP connection step by step."""

import asyncio
import json
import os
import sys

# Step 1: Check how the key is loaded
print("=" * 60)
print("STEP 1: Key loading")
print("=" * 60)

# Check all sources
from pr_review_agent.config import get_config, _find_env_files

env_files = _find_env_files()
print(f"  .env files found: {env_files}")
for f in env_files:
    content = f.read_text()
    for line in content.splitlines():
        if "NOTION" in line.upper():
            key_part = line.split("=", 1)
            if len(key_part) == 2:
                val = key_part[1]
                print(f"  {f}: {key_part[0]}={val[:8]}...{val[-4:]} (len={len(val)})")
                if val.startswith(("'", '"')) or val.endswith(("'", '"')):
                    print(f"  ⚠ WARNING: Value has surrounding quotes!")
                if val != val.strip():
                    print(f"  ⚠ WARNING: Value has leading/trailing whitespace!")

config = get_config()
raw_key = config.notion_api_key
print(f"\n  AgentConfig.notion_api_key: {raw_key[:8]}...{raw_key[-4:]} (len={len(raw_key)})")

env_key = os.environ.get("NOTION_API_KEY", "")
print(f"  os.environ NOTION_API_KEY: {env_key[:8]}...{env_key[-4:]} (len={len(env_key)})")

# Step 2: Check what the client does with it
print("\n" + "=" * 60)
print("STEP 2: Client key processing")
print("=" * 60)

from pr_review_agent.notion.client import NotionMCPClient

client = NotionMCPClient(notion_api_key=config.notion_api_key)
processed_key = client._api_key
print(f"  After strip(): {processed_key[:8]}...{processed_key[-4:]} (len={len(processed_key)})")

if not processed_key.startswith(("ntn_", "secret_")):
    print(f"  ⚠ WARNING: Key doesn't start with 'ntn_' or 'secret_' — may be invalid format")

# Step 3: Check the OPENAPI_MCP_HEADERS value
print("\n" + "=" * 60)
print("STEP 3: OPENAPI_MCP_HEADERS construction")
print("=" * 60)

headers_json = f'{{"Authorization": "Bearer {processed_key}", "Notion-Version": "2022-06-28"}}'
print(f"  Raw string: {headers_json[:50]}...")

try:
    parsed = json.loads(headers_json)
    print(f"  ✓ Valid JSON")
    auth = parsed["Authorization"]
    print(f"  Authorization: {auth[:20]}...{auth[-4:]}")
    print(f"  Notion-Version: {parsed['Notion-Version']}")
except json.JSONDecodeError as e:
    print(f"  ✗ INVALID JSON: {e}")
    print(f"  This is likely the cause of the 401!")

# Step 4: Test direct Notion API call (bypasses MCP entirely)
print("\n" + "=" * 60)
print("STEP 4: Direct Notion API test (no MCP)")
print("=" * 60)

try:
    import urllib.request
    req = urllib.request.Request(
        "https://api.notion.com/v1/users/me",
        headers={
            "Authorization": f"Bearer {processed_key}",
            "Notion-Version": "2022-06-28",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        print(f"  ✓ API key is VALID — authenticated as: {data.get('name', 'unknown')}")
        print(f"    type: {data.get('type', '?')}, id: {data.get('id', '?')}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"  ✗ HTTP {e.code}: {body[:200]}")
    if e.code == 401:
        print(f"\n  The key itself is invalid — Notion rejects it before MCP is involved.")
        print(f"  → Go to https://www.notion.so/my-integrations and verify the token.")
except Exception as e:
    print(f"  ✗ Connection error: {e}")

# Step 5: Test MCP server spawn + tool call
print("\n" + "=" * 60)
print("STEP 5: MCP server connection test")
print("=" * 60)


async def test_mcp():
    client = NotionMCPClient(notion_api_key=config.notion_api_key)
    try:
        async with client.connect() as c:
            print("  ✓ MCP server connected and initialized")

            # Try a minimal search
            result = await c._session.call_tool("API-post-search", {"query": "test"})
            print(f"  call_tool returned: isError={getattr(result, 'isError', 'N/A')}")
            if hasattr(result, "content"):
                for block in result.content:
                    if hasattr(block, "text"):
                        text = block.text
                        print(f"  Content preview: {text[:200]}")
                        if "401" in text or "Unauthorized" in text:
                            print(f"\n  ✗ MCP server connected fine, but Notion API rejected the request.")
                            print(f"    The OPENAPI_MCP_HEADERS env var may not be reaching the server correctly.")
                        break
    except Exception as e:
        print(f"  ✗ {e}")


asyncio.run(test_mcp())

print("\n" + "=" * 60)
print("Done.")
print("=" * 60)
