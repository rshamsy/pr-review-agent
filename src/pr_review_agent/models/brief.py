"""Review brief models — LLM-generated comparison of intent vs implementation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntentDelta(BaseModel):
    aspect: str
    intended: str
    implemented: str
    status: Literal["match", "partial", "missing", "extra"]


class ReviewBrief(BaseModel):
    summary: str = ""
    what_was_requested: list[str] = Field(default_factory=list)
    what_was_implemented: list[str] = Field(default_factory=list)
    deltas: list[IntentDelta] = Field(default_factory=list)
    llm_recommendation: Literal["approve", "request_changes", "needs_discussion"] = "needs_discussion"
    llm_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    key_concerns: list[str] = Field(default_factory=list)
    positive_findings: list[str] = Field(default_factory=list)
