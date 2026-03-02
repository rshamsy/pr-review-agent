"""Tests for the migration analyzer module."""

from __future__ import annotations

import pytest

from pr_review_agent.analyzers.migration_analyzer import (
    analyze_migration,
    assess_migration_risk,
    assess_rollback_complexity,
    detect_migrations,
    parse_migration_sql,
)
from pr_review_agent.models.migration import MigrationInfo, MigrationOperation
from pr_review_agent.models.pr import FileChange


# ---------------------------------------------------------------------------
# parse_migration_sql
# ---------------------------------------------------------------------------


class TestParseMigrationSQL:
    """Tests for parse_migration_sql()."""

    def test_create_table(self):
        sql = 'CREATE TABLE "users" ("id" TEXT NOT NULL);'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "CREATE_TABLE"
        assert ops[0].table == "users"
        assert ops[0].destructive is False

    def test_create_table_without_quotes(self):
        sql = "CREATE TABLE users (id TEXT NOT NULL);"
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "CREATE_TABLE"
        assert ops[0].table == "users"

    def test_drop_table(self):
        sql = 'DROP TABLE "orders";'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "DROP_TABLE"
        assert ops[0].table == "orders"
        assert ops[0].destructive is True

    def test_drop_table_without_quotes(self):
        sql = "DROP TABLE orders;"
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "DROP_TABLE"
        assert ops[0].table == "orders"
        assert ops[0].destructive is True

    def test_alter_table_add_column(self):
        sql = 'ALTER TABLE "users" ADD COLUMN "email" TEXT;'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "ADD_COLUMN"
        assert ops[0].table == "users"
        assert ops[0].destructive is False

    def test_alter_table_add_column_not_null_without_default(self):
        sql = 'ALTER TABLE "users" ADD COLUMN "email" TEXT NOT NULL;'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "ADD_COLUMN"
        assert ops[0].table == "users"
        assert ops[0].destructive is True

    def test_alter_table_add_column_not_null_with_default(self):
        sql = "ALTER TABLE \"users\" ADD COLUMN \"status\" TEXT NOT NULL DEFAULT 'active';"
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "ADD_COLUMN"
        assert ops[0].table == "users"
        assert ops[0].destructive is False

    def test_alter_table_drop_column(self):
        sql = 'ALTER TABLE "users" DROP COLUMN "legacy_field";'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "DROP_COLUMN"
        assert ops[0].table == "users"
        assert ops[0].destructive is True

    def test_alter_column_with_type_change(self):
        sql = 'ALTER TABLE "products" ALTER COLUMN "price" TYPE DECIMAL(10,2);'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "ALTER_COLUMN"
        assert ops[0].table == "products"
        assert ops[0].destructive is True

    def test_alter_column_without_type_change(self):
        sql = 'ALTER TABLE "products" ALTER COLUMN "name" SET NOT NULL;'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "ALTER_COLUMN"
        assert ops[0].table == "products"
        assert ops[0].destructive is False

    def test_create_index(self):
        sql = 'CREATE INDEX "idx_users_email" ON "users"("email");'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "CREATE_INDEX"
        assert ops[0].table == "users"
        assert ops[0].destructive is False

    def test_create_unique_index(self):
        sql = 'CREATE UNIQUE INDEX "idx_users_email_unique" ON "users"("email");'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "CREATE_INDEX"
        assert ops[0].table == "users"

    def test_add_constraint(self):
        sql = 'ALTER TABLE "orders" ADD CONSTRAINT "fk_user" FOREIGN KEY ("user_id") REFERENCES "users"("id");'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "ADD_CONSTRAINT"
        assert ops[0].table == "orders"
        assert ops[0].destructive is False

    def test_multiple_statements(self):
        sql = (
            'CREATE TABLE "payments" ("id" TEXT NOT NULL);\n'
            'CREATE INDEX "payments_idx" ON "payments"("id");\n'
            'ALTER TABLE "users" ADD COLUMN "payment_id" TEXT;'
        )
        ops = parse_migration_sql(sql)
        assert len(ops) == 3
        assert ops[0].type == "CREATE_TABLE"
        assert ops[1].type == "CREATE_INDEX"
        assert ops[2].type == "ADD_COLUMN"

    def test_empty_sql(self):
        ops = parse_migration_sql("")
        assert ops == []

    def test_comment_only_sql(self):
        sql = "-- This is a migration comment\n-- Another comment"
        ops = parse_migration_sql(sql)
        assert ops == []

    def test_case_insensitive_parsing(self):
        sql = 'create table "users" ("id" text not null);'
        ops = parse_migration_sql(sql)
        assert len(ops) == 1
        assert ops[0].type == "CREATE_TABLE"

    def test_mixed_comments_and_statements(self):
        sql = (
            "-- Create users table\n"
            'CREATE TABLE "users" ("id" TEXT NOT NULL);\n'
            "-- Add an index\n"
            'CREATE INDEX "idx_users_id" ON "users"("id");'
        )
        ops = parse_migration_sql(sql)
        assert len(ops) == 2
        assert ops[0].type == "CREATE_TABLE"
        assert ops[1].type == "CREATE_INDEX"


# ---------------------------------------------------------------------------
# assess_migration_risk
# ---------------------------------------------------------------------------


class TestAssessMigrationRisk:
    """Tests for assess_migration_risk()."""

    def test_high_risk_drop_table(self):
        ops = [MigrationOperation(type="DROP_TABLE", table="users", details="DROP TABLE users", destructive=True)]
        assert assess_migration_risk(ops) == "high"

    def test_high_risk_drop_column(self):
        ops = [MigrationOperation(type="DROP_COLUMN", table="users", details='ALTER TABLE users DROP COLUMN "email"', destructive=True)]
        assert assess_migration_risk(ops) == "high"

    def test_high_risk_type_change(self):
        ops = [MigrationOperation(
            type="ALTER_COLUMN",
            table="products",
            details='ALTER TABLE "products" ALTER COLUMN "price" TYPE DECIMAL',
            destructive=True,
        )]
        assert assess_migration_risk(ops) == "high"

    def test_medium_risk_not_null_without_default(self):
        ops = [MigrationOperation(
            type="ADD_COLUMN",
            table="users",
            details='ALTER TABLE "users" ADD COLUMN "email" TEXT NOT NULL',
            destructive=True,
        )]
        assert assess_migration_risk(ops) == "medium"

    def test_low_risk_safe_add_column(self):
        ops = [MigrationOperation(
            type="ADD_COLUMN",
            table="users",
            details='ALTER TABLE "users" ADD COLUMN "nickname" TEXT',
            destructive=False,
        )]
        assert assess_migration_risk(ops) == "low"

    def test_low_risk_create_table(self):
        ops = [MigrationOperation(type="CREATE_TABLE", table="payments", details='CREATE TABLE "payments"', destructive=False)]
        assert assess_migration_risk(ops) == "low"

    def test_low_risk_create_index(self):
        ops = [MigrationOperation(type="CREATE_INDEX", table="users", details='CREATE INDEX ON "users"', destructive=False)]
        assert assess_migration_risk(ops) == "low"

    def test_low_risk_add_not_null_with_default(self):
        ops = [MigrationOperation(
            type="ADD_COLUMN",
            table="users",
            details="ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
            destructive=False,
        )]
        assert assess_migration_risk(ops) == "low"

    def test_high_risk_overrides_medium(self):
        """If both high and medium risk ops exist, overall is high."""
        ops = [
            MigrationOperation(type="DROP_TABLE", table="old", details="DROP TABLE old", destructive=True),
            MigrationOperation(
                type="ADD_COLUMN",
                table="users",
                details='ALTER TABLE "users" ADD COLUMN "email" TEXT NOT NULL',
                destructive=True,
            ),
        ]
        assert assess_migration_risk(ops) == "high"

    def test_empty_operations(self):
        assert assess_migration_risk([]) == "low"

    def test_mixed_safe_operations(self):
        ops = [
            MigrationOperation(type="CREATE_TABLE", table="t1", details="CREATE TABLE t1", destructive=False),
            MigrationOperation(type="CREATE_INDEX", table="t1", details='CREATE INDEX ON "t1"', destructive=False),
            MigrationOperation(type="ADD_CONSTRAINT", table="t1", details='ALTER TABLE "t1" ADD CONSTRAINT', destructive=False),
        ]
        assert assess_migration_risk(ops) == "low"


# ---------------------------------------------------------------------------
# assess_rollback_complexity
# ---------------------------------------------------------------------------


class TestAssessRollbackComplexity:
    """Tests for assess_rollback_complexity()."""

    def test_impossible_for_drop_table(self):
        ops = [MigrationOperation(type="DROP_TABLE", table="users", details="DROP TABLE users", destructive=True)]
        assert assess_rollback_complexity(ops) == "impossible"

    def test_impossible_for_drop_column(self):
        ops = [MigrationOperation(type="DROP_COLUMN", table="users", details="DROP COLUMN email", destructive=True)]
        assert assess_rollback_complexity(ops) == "impossible"

    def test_impossible_overrides_all(self):
        """DROP TABLE + type change -> impossible (not hard)."""
        ops = [
            MigrationOperation(type="DROP_TABLE", table="old", details="DROP TABLE old", destructive=True),
            MigrationOperation(
                type="ALTER_COLUMN",
                table="p",
                details='ALTER TABLE "p" ALTER COLUMN "x" TYPE INT',
                destructive=True,
            ),
        ]
        assert assess_rollback_complexity(ops) == "impossible"

    def test_hard_for_type_change(self):
        ops = [MigrationOperation(
            type="ALTER_COLUMN",
            table="products",
            details='ALTER TABLE "products" ALTER COLUMN "price" TYPE DECIMAL',
            destructive=True,
        )]
        assert assess_rollback_complexity(ops) == "hard"

    def test_medium_for_constraints(self):
        ops = [MigrationOperation(type="ADD_CONSTRAINT", table="orders", details='ALTER TABLE "orders" ADD CONSTRAINT fk', destructive=False)]
        assert assess_rollback_complexity(ops) == "medium"

    def test_easy_for_safe_adds(self):
        ops = [MigrationOperation(type="CREATE_TABLE", table="t", details="CREATE TABLE t", destructive=False)]
        assert assess_rollback_complexity(ops) == "easy"

    def test_easy_for_add_column(self):
        ops = [MigrationOperation(type="ADD_COLUMN", table="t", details='ALTER TABLE t ADD COLUMN "x" TEXT', destructive=False)]
        assert assess_rollback_complexity(ops) == "easy"

    def test_easy_for_create_index(self):
        ops = [MigrationOperation(type="CREATE_INDEX", table="t", details='CREATE INDEX ON "t"', destructive=False)]
        assert assess_rollback_complexity(ops) == "easy"

    def test_empty_operations(self):
        assert assess_rollback_complexity([]) == "easy"

    def test_hard_overrides_medium(self):
        """Type change + constraint -> hard (not medium)."""
        ops = [
            MigrationOperation(
                type="ALTER_COLUMN",
                table="p",
                details='ALTER TABLE "p" ALTER COLUMN "x" TYPE DECIMAL',
                destructive=True,
            ),
            MigrationOperation(type="ADD_CONSTRAINT", table="p", details='ALTER TABLE "p" ADD CONSTRAINT fk', destructive=False),
        ]
        assert assess_rollback_complexity(ops) == "hard"


# ---------------------------------------------------------------------------
# detect_migrations
# ---------------------------------------------------------------------------


class TestDetectMigrations:
    """Tests for detect_migrations() with FileChange fixtures."""

    def test_detects_prisma_migration(self):
        files = [
            FileChange(
                filename="prisma/migrations/20240101_init/migration.sql",
                status="added",
                additions=10,
                patch='+CREATE TABLE "users" ("id" TEXT NOT NULL);',
            ),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 1
        assert migrations[0].path == "prisma/migrations/20240101_init/migration.sql"
        assert len(migrations[0].operations) == 1
        assert migrations[0].operations[0].type == "CREATE_TABLE"

    def test_detects_generic_sql_migration(self):
        files = [
            FileChange(
                filename="migrations/001_create_orders.sql",
                status="added",
                additions=5,
                patch='+CREATE TABLE "orders" ("id" TEXT NOT NULL);',
            ),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 1

    def test_ignores_non_migration_files(self):
        files = [
            FileChange(filename="lib/services/user-service.ts", status="modified", additions=10, patch="+some code"),
            FileChange(filename="app/api/route.ts", status="added", additions=5, patch="+handler"),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 0

    def test_skips_migration_file_with_empty_patch(self):
        files = [
            FileChange(
                filename="prisma/migrations/20240101_init/migration.sql",
                status="added",
                additions=0,
                patch="",
            ),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 0

    def test_skips_migration_file_with_none_patch(self):
        files = [
            FileChange(
                filename="prisma/migrations/20240101_init/migration.sql",
                status="added",
                additions=0,
                patch=None,
            ),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 0

    def test_extracts_sql_from_diff_patch(self):
        """Ensures the +/- prefix is handled correctly from diff output."""
        files = [
            FileChange(
                filename="prisma/migrations/20240101_init/migration.sql",
                status="added",
                additions=5,
                patch=(
                    "@@ -0,0 +1,3 @@\n"
                    '+CREATE TABLE "users" ("id" TEXT NOT NULL);\n'
                    '+CREATE INDEX "idx_users" ON "users"("id");'
                ),
            ),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 1
        assert len(migrations[0].operations) == 2
        assert migrations[0].operations[0].type == "CREATE_TABLE"
        assert migrations[0].operations[1].type == "CREATE_INDEX"

    def test_multiple_migration_files(self):
        files = [
            FileChange(
                filename="prisma/migrations/20240101_a/migration.sql",
                status="added",
                additions=5,
                patch='+CREATE TABLE "users" ("id" TEXT);',
            ),
            FileChange(
                filename="prisma/migrations/20240102_b/migration.sql",
                status="added",
                additions=3,
                patch='+DROP TABLE "legacy";',
            ),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 2
        assert migrations[0].risk_level == "low"
        assert migrations[1].risk_level == "high"

    def test_mixed_migration_and_non_migration_files(self):
        files = [
            FileChange(filename="lib/services/user-service.ts", status="modified", additions=10, patch="+code"),
            FileChange(
                filename="prisma/migrations/20240101_init/migration.sql",
                status="added",
                additions=5,
                patch='+CREATE TABLE "users" ("id" TEXT);',
            ),
            FileChange(filename="components/Header.tsx", status="modified", additions=3, patch="+jsx"),
        ]
        migrations = detect_migrations(files)
        assert len(migrations) == 1


# ---------------------------------------------------------------------------
# analyze_migration
# ---------------------------------------------------------------------------


class TestAnalyzeMigration:
    """Tests for analyze_migration() end-to-end."""

    def test_returns_correct_migration_info(self):
        path = "prisma/migrations/20240101_add_users/migration.sql"
        sql = 'CREATE TABLE "users" ("id" TEXT NOT NULL);\nCREATE INDEX "idx" ON "users"("id");'
        info = analyze_migration(path, sql)

        assert isinstance(info, MigrationInfo)
        assert info.path == path
        assert info.name == "20240101_add_users"
        assert info.sql == sql
        assert info.risk_level == "low"
        assert info.rollback_complexity == "easy"
        assert len(info.operations) == 2

    def test_high_risk_migration(self):
        path = "prisma/migrations/20240101_drop_legacy/migration.sql"
        sql = 'DROP TABLE "legacy_data";'
        info = analyze_migration(path, sql)

        assert info.risk_level == "high"
        assert info.rollback_complexity == "impossible"
        assert len(info.warnings) > 0
        assert any("DROP TABLE" in w for w in info.warnings)

    def test_medium_risk_migration(self):
        path = "prisma/migrations/20240101_add_col/migration.sql"
        sql = 'ALTER TABLE "users" ADD COLUMN "email" TEXT NOT NULL;'
        info = analyze_migration(path, sql)

        assert info.risk_level == "medium"
        assert info.rollback_complexity == "easy"
        assert len(info.warnings) > 0
        assert any("NOT NULL" in w for w in info.warnings)

    def test_name_extraction_with_short_path(self):
        path = "migration.sql"
        sql = 'CREATE TABLE "t" ("id" TEXT);'
        info = analyze_migration(path, sql)
        assert info.name == "unknown"

    def test_name_extraction_with_nested_path(self):
        path = "prisma/migrations/20240501_payments/migration.sql"
        sql = 'CREATE TABLE "payments" ("id" TEXT);'
        info = analyze_migration(path, sql)
        assert info.name == "20240501_payments"

    def test_complex_migration(self):
        path = "prisma/migrations/20240101_complex/migration.sql"
        sql = (
            'CREATE TABLE "orders" ("id" TEXT NOT NULL);\n'
            'ALTER TABLE "orders" ADD COLUMN "total" DECIMAL NOT NULL DEFAULT 0;\n'
            'CREATE INDEX "idx_orders" ON "orders"("id");\n'
            'ALTER TABLE "orders" ADD CONSTRAINT "fk_user" FOREIGN KEY ("user_id") REFERENCES "users"("id");'
        )
        info = analyze_migration(path, sql)

        assert info.risk_level == "low"
        assert info.rollback_complexity == "medium"  # constraint present
        assert len(info.operations) == 4

    def test_warnings_for_index_creation(self):
        path = "prisma/migrations/20240101_idx/migration.sql"
        sql = 'CREATE INDEX "idx_big_table" ON "big_table"("col");'
        info = analyze_migration(path, sql)

        assert any("index" in w.lower() for w in info.warnings)

    def test_destructive_migration_with_type_change(self):
        path = "prisma/migrations/20240101_alter/migration.sql"
        sql = 'ALTER TABLE "products" ALTER COLUMN "price" TYPE DECIMAL(10,2);'
        info = analyze_migration(path, sql)

        assert info.risk_level == "high"
        assert info.rollback_complexity == "hard"
        assert any("type change" in w.lower() for w in info.warnings)
