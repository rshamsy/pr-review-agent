"""Notion context models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NotionSearchResult(BaseModel):
    page_id: str
    title: str
    url: str = ""
    content: str = ""


class RelevanceScore(BaseModel):
    page_id: str
    title: str
    url: str = ""
    content: str = ""
    score: float = Field(ge=0, le=10)
    explanation: str = ""
    key_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    relevant_excerpts: list[str] = Field(default_factory=list)


class NotionContext(BaseModel):
    page_id: str
    page_url: str = ""
    title: str
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    raw_content: str = ""
