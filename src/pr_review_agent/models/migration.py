"""Migration data models — ported from types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MigrationOperation(BaseModel):
    type: Literal[
        "CREATE_TABLE",
        "ALTER_TABLE",
        "DROP_TABLE",
        "ADD_COLUMN",
        "DROP_COLUMN",
        "ALTER_COLUMN",
        "CREATE_INDEX",
        "ADD_CONSTRAINT",
        "OTHER",
    ]
    table: str
    details: str
    destructive: bool = False


class MigrationInfo(BaseModel):
    path: str
    name: str
    sql: str = ""
    risk_level: Literal["high", "medium", "low"] = "low"
    operations: list[MigrationOperation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rollback_complexity: Literal["easy", "medium", "hard", "impossible"] = "easy"
