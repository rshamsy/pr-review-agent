"""LangGraph agent state schema."""

from __future__ import annotations

from typing import TypedDict

from pr_review_agent.models.brief import ReviewBrief
from pr_review_agent.models.notion import NotionContext, NotionSearchResult, RelevanceScore
from pr_review_agent.models.pr import PRAnalysis, PRData
from pr_review_agent.models.review import ReviewRecommendation, TestingChecklistItem


class AgentState(TypedDict, total=False):
    pr_number: int
    pr_data: PRData
    ci_status: dict
    diff_text: str
    pr_summary: str
    notion_results: list[NotionSearchResult]
    relevance_scores: list[RelevanceScore]
    notion_contexts: list[NotionContext]
    supplementary_contexts: list[NotionContext]
    user_confirmation: str  # "confirmed" | "provide_url" | "partial" | "exit"
    user_provided_url: str | None
    pr_analysis: PRAnalysis
    testing_checklist: list[TestingChecklistItem]
    review_brief: ReviewBrief
    recommendation: ReviewRecommendation
    markdown_comment: str
    should_block: bool
    status: str  # "running" | "complete" | "blocked" | "error"
    error: str | None
    verbose: bool
    post_comment: bool
    model: str
