"""PR data models — ported from types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FileChange(BaseModel):
    filename: str
    status: Literal["added", "modified", "removed"]
    additions: int = 0
    deletions: int = 0
    patch: str | None = None


class PRData(BaseModel):
    number: int
    title: str
    author: str
    additions: int = 0
    deletions: int = 0
    files: list[FileChange] = Field(default_factory=list)
    branch: str = ""


class ServiceChangeInfo(BaseModel):
    path: str
    basename: str
    is_new: bool = False
    has_tests: bool = False
    lines_changed: int = 0
    content: str = ""
    contains_financial_logic: bool = False


class APIRouteInfo(BaseModel):
    path: str
    endpoint: str
    methods: list[str] = Field(default_factory=list)
    is_new: bool = False
    lines_of_logic: int = 0
    has_business_logic: bool = False
    has_tests: bool = False


class UIChangeInfo(BaseModel):
    path: str
    type: Literal["page", "component"]
    is_new: bool = False
    has_state: bool = False
    has_effects: bool = False
    lines_changed: int = 0


class TestFileInfo(BaseModel):
    path: str
    tested_file: str


class CICheck(BaseModel):
    name: str
    status: Literal["success", "failure", "pending"]
    conclusion: str | None = None


class CIStatus(BaseModel):
    all_passed: bool
    checks: list[CICheck] = Field(default_factory=list)


class PRAnalysis(BaseModel):
    classification: Literal["major", "minor", "trivial"] = "trivial"
    migrations: list = Field(default_factory=list)  # list[MigrationInfo] — avoid circular
    services: list[ServiceChangeInfo] = Field(default_factory=list)
    api_routes: list[APIRouteInfo] = Field(default_factory=list)
    ui_changes: list[UIChangeInfo] = Field(default_factory=list)
    test_files: list[TestFileInfo] = Field(default_factory=list)
    risks: list = Field(default_factory=list)  # list[Risk]
    missing_tests: list = Field(default_factory=list)  # list[MissingTest]
    total_additions: int = 0
    total_deletions: int = 0
