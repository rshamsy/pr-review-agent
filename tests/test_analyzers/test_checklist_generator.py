"""Tests for the checklist generator module."""

from __future__ import annotations

import pytest

from pr_review_agent.analyzers.checklist_generator import (
    format_checklist,
    generate_api_tests,
    generate_edge_case_tests,
    generate_migration_checks,
    generate_pre_flight_checks,
    generate_service_tests,
    generate_testing_checklist,
    generate_ui_tests,
)
from pr_review_agent.models.migration import MigrationInfo, MigrationOperation
from pr_review_agent.models.pr import (
    APIRouteInfo,
    PRAnalysis,
    ServiceChangeInfo,
    UIChangeInfo,
)
from pr_review_agent.models.review import TestingChecklistItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis(
    services: list[ServiceChangeInfo] | None = None,
    api_routes: list[APIRouteInfo] | None = None,
    ui_changes: list[UIChangeInfo] | None = None,
    migrations: list[MigrationInfo] | None = None,
) -> PRAnalysis:
    """Build a minimal PRAnalysis for testing."""
    return PRAnalysis(
        classification="minor",
        services=services or [],
        api_routes=api_routes or [],
        ui_changes=ui_changes or [],
        migrations=migrations or [],
    )


# ---------------------------------------------------------------------------
# generate_testing_checklist
# ---------------------------------------------------------------------------


class TestGenerateTestingChecklist:
    """Tests for generate_testing_checklist()."""

    def test_always_includes_pre_flight_checks(self):
        analysis = _make_analysis()
        checklist = generate_testing_checklist(42, analysis)
        pre_flight = [c for c in checklist if c.category == "pre-flight"]
        assert len(pre_flight) == 3
        # Verify PR number is referenced
        assert any("42" in c.description for c in pre_flight)

    def test_includes_migration_checks(self):
        migration = MigrationInfo(
            path="prisma/migrations/001/migration.sql",
            name="001",
            sql='CREATE TABLE "t" ("id" TEXT);',
            risk_level="low",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table="t", details="CREATE TABLE t", destructive=False),
            ],
        )
        analysis = _make_analysis(migrations=[migration])
        checklist = generate_testing_checklist(1, analysis)
        data_checks = [c for c in checklist if c.category == "data"]
        assert len(data_checks) >= 1
        assert any("migration" in c.description.lower() for c in data_checks)

    def test_includes_migration_create_table_check(self):
        migration = MigrationInfo(
            path="prisma/migrations/001/migration.sql",
            name="001",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table="users", details="CREATE TABLE users", destructive=False),
            ],
        )
        analysis = _make_analysis(migrations=[migration])
        checklist = generate_testing_checklist(1, analysis)
        assert any("new database tables" in c.description.lower() for c in checklist)

    def test_includes_migration_add_column_check(self):
        migration = MigrationInfo(
            path="prisma/migrations/001/migration.sql",
            name="001",
            operations=[
                MigrationOperation(type="ADD_COLUMN", table="users", details="ADD COLUMN email", destructive=False),
            ],
        )
        analysis = _make_analysis(migrations=[migration])
        checklist = generate_testing_checklist(1, analysis)
        assert any("new columns" in c.description.lower() for c in checklist)

    def test_includes_service_tests(self):
        service = ServiceChangeInfo(
            path="lib/services/payment-service.ts",
            basename="payment-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
            contains_financial_logic=True,
        )
        analysis = _make_analysis(services=[service])
        checklist = generate_testing_checklist(1, analysis)
        calc_checks = [c for c in checklist if c.category == "calculation"]
        assert len(calc_checks) >= 1

    def test_includes_api_route_tests(self):
        route = APIRouteInfo(
            path="app/api/orders/route.ts",
            endpoint="/orders",
            methods=["GET", "POST"],
            is_new=True,
            lines_of_logic=50,
            has_business_logic=True,
        )
        analysis = _make_analysis(api_routes=[route])
        checklist = generate_testing_checklist(1, analysis)
        integration = [c for c in checklist if c.category == "integration"]
        assert len(integration) == 2  # one per method
        assert any("GET" in c.description for c in integration)
        assert any("POST" in c.description for c in integration)

    def test_includes_ui_tests_for_new_page(self):
        ui = UIChangeInfo(
            path="app/dashboard/page.tsx",
            type="page",
            is_new=True,
            has_state=True,
            has_effects=False,
            lines_changed=80,
        )
        analysis = _make_analysis(ui_changes=[ui])
        checklist = generate_testing_checklist(1, analysis)
        ui_checks = [c for c in checklist if c.category == "ui"]
        assert len(ui_checks) >= 1
        # Should have navigate + interactive features checks
        assert any("Navigate" in c.description for c in ui_checks)
        assert any("interactive" in c.description.lower() for c in ui_checks)

    def test_includes_edge_case_tests_for_financial_logic(self):
        service = ServiceChangeInfo(
            path="lib/services/pricing.ts",
            basename="pricing",
            is_new=True,
            has_tests=False,
            lines_changed=50,
            contains_financial_logic=True,
        )
        analysis = _make_analysis(services=[service])
        checklist = generate_testing_checklist(1, analysis)
        edge_cases = [c for c in checklist if c.category == "edge-case"]
        assert len(edge_cases) >= 1

    def test_no_edge_case_tests_without_financial_logic(self):
        service = ServiceChangeInfo(
            path="lib/services/auth.ts",
            basename="auth",
            is_new=True,
            has_tests=False,
            lines_changed=50,
        )
        analysis = _make_analysis(services=[service])
        checklist = generate_testing_checklist(1, analysis)
        edge_cases = [c for c in checklist if c.category == "edge-case"]
        assert len(edge_cases) == 0

    def test_empty_analysis_only_pre_flight(self):
        analysis = _make_analysis()
        checklist = generate_testing_checklist(1, analysis)
        assert all(c.category == "pre-flight" for c in checklist)
        assert len(checklist) == 3

    def test_comprehensive_pr(self):
        """A PR with migrations, services, routes, and UI should produce a rich checklist."""
        migration = MigrationInfo(
            path="prisma/migrations/001/migration.sql",
            name="001",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table="payments", details="CREATE TABLE payments", destructive=False),
                MigrationOperation(type="ADD_COLUMN", table="users", details="ADD COLUMN email", destructive=False),
            ],
        )
        service = ServiceChangeInfo(
            path="lib/services/payment-service.ts",
            basename="payment-service",
            is_new=True,
            has_tests=False,
            lines_changed=200,
            contains_financial_logic=True,
        )
        route = APIRouteInfo(
            path="app/api/payments/route.ts",
            endpoint="/payments",
            methods=["GET", "POST"],
            is_new=True,
            lines_of_logic=80,
            has_business_logic=True,
        )
        ui = UIChangeInfo(
            path="app/payments/page.tsx",
            type="page",
            is_new=True,
            has_state=True,
            has_effects=True,
            lines_changed=120,
        )
        analysis = _make_analysis(
            migrations=[migration],
            services=[service],
            api_routes=[route],
            ui_changes=[ui],
        )
        checklist = generate_testing_checklist(1, analysis)

        categories = {c.category for c in checklist}
        assert "pre-flight" in categories
        assert "data" in categories
        assert "calculation" in categories
        assert "integration" in categories
        assert "ui" in categories
        assert "edge-case" in categories


# ---------------------------------------------------------------------------
# Priority sorting
# ---------------------------------------------------------------------------


class TestPrioritySorting:
    """Tests for priority-based sorting of checklist items."""

    def test_must_items_come_first(self):
        service = ServiceChangeInfo(
            path="lib/services/payment-service.ts",
            basename="payment-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
            contains_financial_logic=True,
        )
        analysis = _make_analysis(services=[service])
        checklist = generate_testing_checklist(1, analysis)

        # All "must" items should appear before any "should" or "nice-to-have"
        priorities = [c.priority for c in checklist]
        first_should = next((i for i, p in enumerate(priorities) if p == "should"), len(priorities))
        first_nice = next((i for i, p in enumerate(priorities) if p == "nice-to-have"), len(priorities))
        last_must = max((i for i, p in enumerate(priorities) if p == "must"), default=-1)

        if last_must >= 0 and first_should < len(priorities):
            assert last_must < first_should
        if last_must >= 0 and first_nice < len(priorities):
            assert last_must < first_nice

    def test_should_items_before_nice_to_have(self):
        service = ServiceChangeInfo(
            path="lib/services/payment-service.ts",
            basename="payment-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
            contains_financial_logic=True,
        )
        analysis = _make_analysis(services=[service])
        checklist = generate_testing_checklist(1, analysis)

        priorities = [c.priority for c in checklist]
        first_nice = next((i for i, p in enumerate(priorities) if p == "nice-to-have"), len(priorities))
        last_should = max((i for i, p in enumerate(priorities) if p == "should"), default=-1)

        if last_should >= 0 and first_nice < len(priorities):
            assert last_should < first_nice

    def test_sorting_is_stable_within_priority(self):
        """Items with the same priority should maintain relative order."""
        analysis = _make_analysis()
        checklist = generate_testing_checklist(99, analysis)
        # All pre-flight items are "must" priority; they should keep their order
        pre_flight = [c for c in checklist if c.category == "pre-flight"]
        assert len(pre_flight) == 3
        assert "deployment" in pre_flight[0].description.lower()
        assert "database" in pre_flight[1].description.lower()
        assert "environment" in pre_flight[2].description.lower()


# ---------------------------------------------------------------------------
# format_checklist
# ---------------------------------------------------------------------------


class TestFormatChecklist:
    """Tests for format_checklist()."""

    def test_header_present(self):
        output = format_checklist([])
        assert "BROWSER TESTING CHECKLIST" in output

    def test_pre_flight_section(self):
        items = [
            TestingChecklistItem(category="pre-flight", description="Check deployment", priority="must"),
        ]
        output = format_checklist(items)
        assert "PRE-FLIGHT (CRITICAL)" in output
        assert "[ ] Check deployment" in output

    def test_must_section(self):
        items = [
            TestingChecklistItem(category="integration", description="Test GET /users", priority="must"),
        ]
        output = format_checklist(items)
        assert "MUST TEST" in output
        assert "[ ] Test GET /users" in output

    def test_should_section(self):
        items = [
            TestingChecklistItem(category="data", description="Verify columns", priority="should"),
        ]
        output = format_checklist(items)
        assert "SHOULD TEST" in output
        assert "[ ] Verify columns" in output

    def test_nice_to_have_section(self):
        items = [
            TestingChecklistItem(category="edge-case", description="Test large dataset", priority="nice-to-have"),
        ]
        output = format_checklist(items)
        assert "NICE TO HAVE" in output
        assert "[ ] Test large dataset" in output

    def test_url_appended(self):
        items = [
            TestingChecklistItem(
                category="integration",
                description="Test GET /users",
                url="/users",
                priority="must",
            ),
        ]
        output = format_checklist(items)
        assert "[ ] Test GET /users (/users)" in output

    def test_no_url_no_parentheses(self):
        items = [
            TestingChecklistItem(category="data", description="Check data", priority="must"),
        ]
        output = format_checklist(items)
        assert "[ ] Check data" in output
        assert "()" not in output

    def test_empty_sections_omitted(self):
        items = [
            TestingChecklistItem(category="pre-flight", description="Deploy check", priority="must"),
        ]
        output = format_checklist(items)
        assert "PRE-FLIGHT (CRITICAL)" in output
        assert "MUST TEST" not in output  # no non-pre-flight must items
        assert "SHOULD TEST" not in output
        assert "NICE TO HAVE" not in output

    def test_full_checklist_formatting(self):
        items = [
            TestingChecklistItem(category="pre-flight", description="Verify deploy", priority="must"),
            TestingChecklistItem(category="integration", description="Test POST /api", url="/api", priority="must"),
            TestingChecklistItem(category="data", description="Verify columns", priority="should"),
            TestingChecklistItem(category="edge-case", description="Test edge case", priority="nice-to-have"),
        ]
        output = format_checklist(items)
        assert "PRE-FLIGHT (CRITICAL)" in output
        assert "MUST TEST" in output
        assert "SHOULD TEST" in output
        assert "NICE TO HAVE" in output

    def test_multiple_items_per_section(self):
        items = [
            TestingChecklistItem(category="pre-flight", description="Check A", priority="must"),
            TestingChecklistItem(category="pre-flight", description="Check B", priority="must"),
        ]
        output = format_checklist(items)
        assert "[ ] Check A" in output
        assert "[ ] Check B" in output


# ---------------------------------------------------------------------------
# generate_edge_case_tests
# ---------------------------------------------------------------------------


class TestGenerateEdgeCaseTests:
    """Tests for generate_edge_case_tests()."""

    def test_returns_edge_case_items(self):
        items = generate_edge_case_tests()
        assert len(items) == 3
        assert all(item.category == "edge-case" for item in items)

    def test_includes_zero_null_test(self):
        items = generate_edge_case_tests()
        assert any("zero" in item.description.lower() or "null" in item.description.lower() for item in items)

    def test_includes_large_dataset_test(self):
        items = generate_edge_case_tests()
        assert any("large dataset" in item.description.lower() for item in items)

    def test_includes_error_handling_test(self):
        items = generate_edge_case_tests()
        assert any("error" in item.description.lower() for item in items)

    def test_priorities(self):
        items = generate_edge_case_tests()
        priorities = {item.priority for item in items}
        assert "should" in priorities
        assert "nice-to-have" in priorities

    def test_financial_logic_triggers_edge_cases_in_checklist(self):
        """When financial logic is present, edge case tests are added to the checklist."""
        service = ServiceChangeInfo(
            path="lib/services/pricing.ts",
            basename="pricing",
            is_new=True,
            has_tests=False,
            lines_changed=50,
            contains_financial_logic=True,
        )
        analysis = _make_analysis(services=[service])
        checklist = generate_testing_checklist(1, analysis)
        edge_cases = [c for c in checklist if c.category == "edge-case"]
        assert len(edge_cases) == 3

    def test_no_financial_logic_no_edge_cases(self):
        """Without financial logic, no edge case tests are generated."""
        service = ServiceChangeInfo(
            path="lib/services/auth.ts",
            basename="auth",
            is_new=True,
            has_tests=False,
            lines_changed=50,
        )
        analysis = _make_analysis(services=[service])
        checklist = generate_testing_checklist(1, analysis)
        edge_cases = [c for c in checklist if c.category == "edge-case"]
        assert len(edge_cases) == 0


# ---------------------------------------------------------------------------
# Service-specific checklist tests
# ---------------------------------------------------------------------------


class TestServiceSpecificChecks:
    """Test generate_service_tests for domain-specific services."""

    def test_payment_service_gets_calculation_check(self):
        service = ServiceChangeInfo(
            path="lib/services/payment-service.ts",
            basename="payment-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
        )
        tests = generate_service_tests(service)
        assert any(c.category == "calculation" for c in tests)

    def test_supplier_service_gets_calculation_check(self):
        service = ServiceChangeInfo(
            path="lib/services/supplier-payments.ts",
            basename="supplier-payments",
            is_new=True,
            has_tests=False,
            lines_changed=100,
        )
        tests = generate_service_tests(service)
        assert any(c.category == "calculation" for c in tests)

    def test_csv_service_gets_csv_check(self):
        service = ServiceChangeInfo(
            path="lib/services/payment-csv.ts",
            basename="payment-csv",
            is_new=True,
            has_tests=False,
            lines_changed=100,
            content="export function toCSV(data) {}",
        )
        tests = generate_service_tests(service)
        assert any("csv" in c.description.lower() for c in tests)

    def test_receipt_service_gets_weight_check(self):
        service = ServiceChangeInfo(
            path="lib/services/receipt-service.ts",
            basename="receipt-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
        )
        tests = generate_service_tests(service)
        assert any("weight" in c.description.lower() for c in tests)

    def test_bale_service_gets_bale_check(self):
        service = ServiceChangeInfo(
            path="lib/services/bale-production-service.ts",
            basename="bale-production-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
        )
        tests = generate_service_tests(service)
        assert any("bale" in c.description.lower() for c in tests)

    def test_generic_service_gets_no_specific_checks(self):
        service = ServiceChangeInfo(
            path="lib/services/auth-service.ts",
            basename="auth-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
        )
        tests = generate_service_tests(service)
        assert len(tests) == 0


# ---------------------------------------------------------------------------
# API route checklist tests
# ---------------------------------------------------------------------------


class TestAPIRouteChecks:
    """Test generate_api_tests for API routes."""

    def test_generates_check_per_method(self):
        route = APIRouteInfo(
            path="app/api/users/route.ts",
            endpoint="/users",
            methods=["GET", "POST", "DELETE"],
            is_new=True,
            lines_of_logic=50,
            has_business_logic=True,
        )
        tests = generate_api_tests(route)
        assert len(tests) == 3
        methods_in_desc = {t.description.split()[1] for t in tests}
        assert methods_in_desc == {"GET", "POST", "DELETE"}

    def test_must_priority_for_business_logic(self):
        route = APIRouteInfo(
            path="app/api/orders/route.ts",
            endpoint="/orders",
            methods=["POST"],
            is_new=True,
            lines_of_logic=50,
            has_business_logic=True,
        )
        tests = generate_api_tests(route)
        assert all(t.priority == "must" for t in tests)

    def test_should_priority_without_business_logic(self):
        route = APIRouteInfo(
            path="app/api/health/route.ts",
            endpoint="/health",
            methods=["GET"],
            is_new=True,
            lines_of_logic=5,
            has_business_logic=False,
        )
        tests = generate_api_tests(route)
        assert all(t.priority == "should" for t in tests)

    def test_url_set_on_api_checks(self):
        route = APIRouteInfo(
            path="app/api/users/route.ts",
            endpoint="/users",
            methods=["GET"],
            is_new=True,
            lines_of_logic=10,
            has_business_logic=False,
        )
        tests = generate_api_tests(route)
        assert tests[0].url == "/users"

    def test_no_methods_no_checks(self):
        route = APIRouteInfo(
            path="app/api/empty/route.ts",
            endpoint="/empty",
            methods=[],
            is_new=True,
            lines_of_logic=5,
            has_business_logic=False,
        )
        tests = generate_api_tests(route)
        assert len(tests) == 0


# ---------------------------------------------------------------------------
# UI checklist tests
# ---------------------------------------------------------------------------


class TestUIChecks:
    """Test generate_ui_tests for UI components."""

    def test_new_page_gets_navigate_check(self):
        ui = UIChangeInfo(
            path="app/dashboard/page.tsx",
            type="page",
            is_new=True,
            has_state=False,
            has_effects=False,
            lines_changed=50,
        )
        tests = generate_ui_tests(ui)
        assert any("Navigate" in t.description for t in tests)

    def test_state_gets_interactive_check(self):
        ui = UIChangeInfo(
            path="components/Counter.tsx",
            type="component",
            is_new=False,
            has_state=True,
            has_effects=False,
            lines_changed=20,
        )
        tests = generate_ui_tests(ui)
        assert any("interactive" in t.description.lower() for t in tests)

    def test_no_new_no_state_no_checks(self):
        ui = UIChangeInfo(
            path="components/Static.tsx",
            type="component",
            is_new=False,
            has_state=False,
            has_effects=False,
            lines_changed=5,
        )
        tests = generate_ui_tests(ui)
        assert len(tests) == 0

    def test_new_page_url_extraction(self):
        ui = UIChangeInfo(
            path="app/settings/profile/page.tsx",
            type="page",
            is_new=True,
            has_state=False,
            has_effects=False,
            lines_changed=30,
        )
        tests = generate_ui_tests(ui)
        navigate = [t for t in tests if "Navigate" in t.description]
        assert len(navigate) == 1
        assert navigate[0].url == "/settings/profile"

    def test_new_page_with_state(self):
        ui = UIChangeInfo(
            path="app/dashboard/page.tsx",
            type="page",
            is_new=True,
            has_state=True,
            has_effects=False,
            lines_changed=80,
        )
        tests = generate_ui_tests(ui)
        assert len(tests) == 2  # navigate + interactive
