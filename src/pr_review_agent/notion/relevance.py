"""Relevance scoring — uses Claude (haiku) to assess Notion page relevance to a PR."""

from __future__ import annotations

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from pr_review_agent.models.notion import NotionContext, RelevanceScore

EXTRACT_SECTIONS_PROMPT = """You are a context extraction assistant. Given a PR summary and a Notion page, extract the sections that are relevant to the PR.

Return the relevant text verbatim, preserving its original formatting. If nothing in the page is relevant to the PR, respond with exactly: NONE"""


def extract_relevant_sections(
    pr_summary: str,
    page_content: str,
    page_title: str = "",
    model: str = "claude-haiku-4-5-20251001",
) -> str | None:
    """Extract sections from a Notion page that are relevant to a PR.

    Uses Claude Haiku to identify and extract relevant portions.
    Returns the extracted text, or None if nothing is relevant.
    """
    if not page_content.strip():
        return None

    llm = ChatAnthropic(model=model, max_tokens=4096, temperature=0)

    truncated_content = page_content[:8000]

    messages = [
        SystemMessage(content=EXTRACT_SECTIONS_PROMPT),
        HumanMessage(content=f"""PR Summary:
{pr_summary}

Notion Page Title: {page_title}

Notion Page Content:
{truncated_content}"""),
    ]

    response = llm.invoke(messages)
    content = response.content if isinstance(response.content, str) else str(response.content)

    if content.strip().upper() == "NONE":
        return None

    return content.strip()


RELEVANCE_SYSTEM_PROMPT = """You are a relevance scoring assistant. Given a PR summary and a Notion page content, assess whether the Notion page describes the intent/requirements behind the PR.

Respond with a JSON object:
{
  "score": <0-10 integer>,
  "explanation": "<brief explanation>",
  "key_matches": ["<aspects that align>"],
  "gaps": ["<aspects missing from the Notion page>"]
}

Scoring guide:
- 9-10: Clearly the spec/requirements for this exact PR
- 7-8: Highly relevant, describes the same feature
- 5-6: Related topic but not specific to this PR
- 3-4: Tangentially related
- 0-2: Not relevant

Respond ONLY with the JSON object, no other text."""


def score_relevance(
    pr_summary: str,
    notion_content: str,
    notion_page_id: str = "",
    notion_title: str = "",
    notion_url: str = "",
    model: str = "claude-haiku-4-5-20251001",
) -> RelevanceScore:
    """Score how relevant a Notion page is to a PR.

    Uses Claude Haiku for cost efficiency — this is just a relevance check.
    """
    llm = ChatAnthropic(model=model, max_tokens=512, temperature=0)

    # Truncate content to avoid excessive tokens
    truncated_content = notion_content[:8000]

    messages = [
        SystemMessage(content=RELEVANCE_SYSTEM_PROMPT),
        HumanMessage(content=f"""PR Summary:
{pr_summary}

Notion Page Title: {notion_title}

Notion Page Content:
{truncated_content}"""),
    ]

    response = llm.invoke(messages)
    content = response.content if isinstance(response.content, str) else str(response.content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
        else:
            data = {"score": 0, "explanation": "Failed to parse relevance response", "key_matches": [], "gaps": []}

    return RelevanceScore(
        page_id=notion_page_id,
        title=notion_title,
        url=notion_url,
        content=notion_content,
        score=min(max(float(data.get("score", 0)), 0), 10),
        explanation=data.get("explanation", ""),
        key_matches=data.get("key_matches", []),
        gaps=data.get("gaps", []),
    )
