"""Migration analyzer — ported from migration-analyzer.ts.

Pure SQL parsing and risk assessment. Gets SQL from diff patches, not disk.
"""

from __future__ import annotations

import re

from pr_review_agent.models.migration import MigrationInfo, MigrationOperation
from pr_review_agent.models.pr import FileChange


def detect_migrations(files: list[FileChange]) -> list[MigrationInfo]:
    """Detect migration files in PR and analyze them."""
    migrations: list[MigrationInfo] = []

    for file in files:
        if not _is_migration_file(file.filename):
            continue

        sql = _extract_sql_from_patch(file.patch or "")
        if not sql:
            continue

        migration = analyze_migration(file.filename, sql)
        migrations.append(migration)

    return migrations


def _is_migration_file(filename: str) -> bool:
    """Check if a file is a migration file."""
    patterns = [
        r"prisma/migrations/.*/migration\.sql$",
        r"migrations/.*\.sql$",
        r"alembic/versions/.*\.py$",
        r"db/migrate/.*\.rb$",
    ]
    return any(re.search(p, filename) for p in patterns)


def _extract_sql_from_patch(patch: str) -> str:
    """Extract SQL content from a diff patch.

    Pulls only added lines (lines starting with +, excluding the +++ header).
    """
    if not patch:
        return ""

    lines: list[str] = []
    for line in patch.split("\n"):
        if line.startswith("+++"):
            continue
        if line.startswith("+"):
            lines.append(line[1:])  # Strip the leading +
        elif not line.startswith("-") and not line.startswith("@@"):
            # Context line — include as-is for parsing completeness
            lines.append(line)

    return "\n".join(lines)


def analyze_migration(path: str, sql: str) -> MigrationInfo:
    """Analyze a single migration file."""
    operations = parse_migration_sql(sql)
    risk_level = assess_migration_risk(operations)
    warnings = generate_migration_warnings(operations)
    rollback_complexity = assess_rollback_complexity(operations)

    # Extract migration name from path
    parts = path.split("/")
    name = parts[2] if len(parts) > 2 else "unknown"

    return MigrationInfo(
        path=path,
        name=name,
        sql=sql,
        risk_level=risk_level,
        operations=operations,
        warnings=warnings,
        rollback_complexity=rollback_complexity,
    )


def parse_migration_sql(sql: str) -> list[MigrationOperation]:
    """Parse SQL statements into migration operations."""
    operations: list[MigrationOperation] = []

    for line in sql.split("\n"):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("--"):
            continue

        # CREATE TABLE
        if re.search(r"CREATE TABLE", trimmed, re.IGNORECASE):
            match = re.search(r'CREATE TABLE\s+"?(\w+)"?', trimmed, re.IGNORECASE)
            table = match.group(1) if match else "unknown"
            operations.append(MigrationOperation(
                type="CREATE_TABLE", table=table, details=trimmed, destructive=False,
            ))

        # DROP TABLE
        elif re.search(r"DROP TABLE", trimmed, re.IGNORECASE):
            match = re.search(r'DROP TABLE\s+"?(\w+)"?', trimmed, re.IGNORECASE)
            table = match.group(1) if match else "unknown"
            operations.append(MigrationOperation(
                type="DROP_TABLE", table=table, details=trimmed, destructive=True,
            ))

        # ALTER TABLE ADD COLUMN
        elif re.search(r"ALTER TABLE.*ADD COLUMN", trimmed, re.IGNORECASE):
            match = re.search(r'ALTER TABLE\s+"?(\w+)"?', trimmed, re.IGNORECASE)
            table = match.group(1) if match else "unknown"
            not_null = "NOT NULL" in trimmed.upper()
            has_default = "DEFAULT" in trimmed.upper()
            operations.append(MigrationOperation(
                type="ADD_COLUMN",
                table=table,
                details=trimmed,
                destructive=not_null and not has_default,
            ))

        # ALTER TABLE DROP COLUMN
        elif re.search(r"ALTER TABLE.*DROP COLUMN", trimmed, re.IGNORECASE):
            match = re.search(r'ALTER TABLE\s+"?(\w+)"?', trimmed, re.IGNORECASE)
            table = match.group(1) if match else "unknown"
            operations.append(MigrationOperation(
                type="DROP_COLUMN", table=table, details=trimmed, destructive=True,
            ))

        # ALTER TABLE ALTER COLUMN
        elif re.search(r"ALTER TABLE.*ALTER COLUMN", trimmed, re.IGNORECASE):
            match = re.search(r'ALTER TABLE\s+"?(\w+)"?', trimmed, re.IGNORECASE)
            table = match.group(1) if match else "unknown"
            type_change = "TYPE" in trimmed.upper()
            operations.append(MigrationOperation(
                type="ALTER_COLUMN",
                table=table,
                details=trimmed,
                destructive=type_change,
            ))

        # CREATE INDEX
        elif re.search(r"CREATE.*INDEX", trimmed, re.IGNORECASE):
            match = re.search(r'ON\s+"?(\w+)"?', trimmed, re.IGNORECASE)
            table = match.group(1) if match else "unknown"
            operations.append(MigrationOperation(
                type="CREATE_INDEX", table=table, details=trimmed, destructive=False,
            ))

        # ADD CONSTRAINT
        elif re.search(r"ADD CONSTRAINT", trimmed, re.IGNORECASE):
            match = re.search(r'ALTER TABLE\s+"?(\w+)"?', trimmed, re.IGNORECASE)
            table = match.group(1) if match else "unknown"
            operations.append(MigrationOperation(
                type="ADD_CONSTRAINT", table=table, details=trimmed, destructive=False,
            ))

    return operations


def assess_migration_risk(operations: list[MigrationOperation]) -> str:
    """Assess overall migration risk level."""
    has_drop_table = any(op.type == "DROP_TABLE" for op in operations)
    has_drop_column = any(op.type == "DROP_COLUMN" for op in operations)
    has_type_change = any(
        op.type == "ALTER_COLUMN" and "TYPE" in op.details.upper() for op in operations
    )

    if has_drop_table or has_drop_column or has_type_change:
        return "high"

    has_destructive = any(op.destructive for op in operations)
    has_add_not_null = any(
        op.type == "ADD_COLUMN"
        and "NOT NULL" in op.details.upper()
        and "DEFAULT" not in op.details.upper()
        for op in operations
    )

    if has_destructive or has_add_not_null:
        return "medium"

    return "low"


def generate_migration_warnings(operations: list[MigrationOperation]) -> list[str]:
    """Generate human-readable warnings for migration operations."""
    warnings: list[str] = []

    for op in operations:
        if op.type == "DROP_TABLE":
            warnings.append(f'DROP TABLE "{op.table}" will permanently delete all data')
        elif op.type == "DROP_COLUMN":
            warnings.append("DROP COLUMN will permanently delete data in that column")
        elif op.type == "ALTER_COLUMN" and "TYPE" in op.details.upper():
            warnings.append("Column type change may fail or lose data if incompatible")
        elif op.type == "ADD_COLUMN":
            if "NOT NULL" in op.details.upper() and "DEFAULT" not in op.details.upper():
                warnings.append("Adding NOT NULL column without DEFAULT may fail on existing data")
        elif op.type == "CREATE_INDEX":
            warnings.append("Creating index may take time on large tables")

    return warnings


def assess_rollback_complexity(operations: list[MigrationOperation]) -> str:
    """Assess how hard it would be to rollback this migration."""
    has_drop_table = any(op.type == "DROP_TABLE" for op in operations)
    has_drop_column = any(op.type == "DROP_COLUMN" for op in operations)

    if has_drop_table or has_drop_column:
        return "impossible"

    has_type_change = any(
        op.type == "ALTER_COLUMN" and "TYPE" in op.details.upper() for op in operations
    )
    if has_type_change:
        return "hard"

    has_constraints = any(op.type == "ADD_CONSTRAINT" for op in operations)
    if has_constraints:
        return "medium"

    return "easy"
