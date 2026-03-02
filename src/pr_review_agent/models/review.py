"""Review recommendation models — ported from types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Risk(BaseModel):
    level: Literal["critical", "high", "medium", "low"]
    category: Literal["database", "business-logic", "security", "test-coverage", "performance"]
    description: str
    file: str | None = None


class MissingTest(BaseModel):
    service_file: str
    reason: Literal[
        "new_service_no_test",
        "modified_service_no_test",
        "critical_logic_no_test",
        "api_route_no_test",
    ]
    severity: Literal["critical", "high", "medium"]
    suggested_test_file: str


class TestingChecklistItem(BaseModel):
    category: Literal["pre-flight", "auth", "ui", "data", "calculation", "integration", "edge-case"]
    description: str
    url: str | None = None
    priority: Literal["must", "should", "nice-to-have"]


class ReviewRecommendation(BaseModel):
    verdict: Literal["approve", "request_changes", "needs_discussion"]
    blockers: list[str] = Field(default_factory=list)
    required: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
