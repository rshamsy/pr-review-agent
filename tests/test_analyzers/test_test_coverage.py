"""Tests for the test coverage analyzer module."""

from __future__ import annotations

import pytest

from pr_review_agent.analyzers.test_coverage import (
    analyze_coverage,
    categorize_severity,
    generate_summary,
    generate_test_recommendations,
    should_flag_service,
)
from pr_review_agent.models.pr import APIRouteInfo, ServiceChangeInfo
from pr_review_agent.models.review import MissingTest


# ---------------------------------------------------------------------------
# analyze_coverage
# ---------------------------------------------------------------------------


class TestAnalyzeCoverage:
    """Tests for analyze_coverage()."""

    def test_no_gaps_returns_empty_and_summary(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/user-service.ts",
                basename="user-service",
                is_new=False,
                has_tests=True,
                lines_changed=20,
            ),
        ]
        missing, summary = analyze_coverage(services, [])
        assert len(missing) == 0
        assert "All services" in summary

    def test_flags_new_service_without_tests(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/new-service.ts",
                basename="new-service",
                is_new=True,
                has_tests=False,
                lines_changed=100,
            ),
        ]
        missing, summary = analyze_coverage(services, [])
        assert len(missing) == 1
        assert missing[0].reason == "new_service_no_test"
        assert missing[0].severity == "high"

    def test_flags_financial_service_without_tests(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/payment-calc.ts",
                basename="payment-calc",
                is_new=False,
                has_tests=False,
                lines_changed=30,
                contains_financial_logic=True,
            ),
        ]
        missing, summary = analyze_coverage(services, [])
        assert len(missing) == 1
        assert missing[0].severity == "critical"
        assert missing[0].reason == "critical_logic_no_test"

    def test_does_not_flag_service_with_tests(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/covered.ts",
                basename="covered",
                is_new=True,
                has_tests=True,
                lines_changed=200,
                contains_financial_logic=True,
            ),
        ]
        missing, _ = analyze_coverage(services, [])
        assert len(missing) == 0

    def test_does_not_flag_small_modified_service(self):
        """Modified service with few lines changed and no special flags."""
        services = [
            ServiceChangeInfo(
                path="lib/services/minor.ts",
                basename="minor",
                is_new=False,
                has_tests=False,
                lines_changed=10,
            ),
        ]
        missing, _ = analyze_coverage(services, [])
        assert len(missing) == 0

    def test_flags_large_modified_service(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/big-change.ts",
                basename="big-change",
                is_new=False,
                has_tests=False,
                lines_changed=80,
            ),
        ]
        missing, _ = analyze_coverage(services, [])
        assert len(missing) == 1
        assert missing[0].severity == "high"  # lines_changed > 50

    def test_flags_api_route_with_business_logic(self):
        routes = [
            APIRouteInfo(
                path="app/api/orders/route.ts",
                endpoint="/orders",
                methods=["POST"],
                is_new=True,
                lines_of_logic=60,
                has_business_logic=True,
            ),
        ]
        missing, _ = analyze_coverage([], routes)
        assert len(missing) == 1
        assert missing[0].reason == "api_route_no_test"
        assert missing[0].severity == "high"  # lines_of_logic > 50

    def test_api_route_medium_severity(self):
        routes = [
            APIRouteInfo(
                path="app/api/items/route.ts",
                endpoint="/items",
                methods=["GET"],
                is_new=True,
                lines_of_logic=35,
                has_business_logic=True,
            ),
        ]
        missing, _ = analyze_coverage([], routes)
        assert len(missing) == 1
        assert missing[0].severity == "medium"

    def test_does_not_flag_api_without_business_logic(self):
        routes = [
            APIRouteInfo(
                path="app/api/health/route.ts",
                endpoint="/health",
                methods=["GET"],
                is_new=True,
                lines_of_logic=5,
                has_business_logic=False,
            ),
        ]
        missing, _ = analyze_coverage([], routes)
        assert len(missing) == 0

    def test_does_not_flag_api_with_few_lines(self):
        """Business logic with < 30 lines_of_logic is not flagged."""
        routes = [
            APIRouteInfo(
                path="app/api/simple/route.ts",
                endpoint="/simple",
                methods=["GET"],
                is_new=True,
                lines_of_logic=20,
                has_business_logic=True,
            ),
        ]
        missing, _ = analyze_coverage([], routes)
        assert len(missing) == 0

    def test_does_not_flag_api_route_with_tests(self):
        """API route with has_tests=True should not be flagged."""
        routes = [
            APIRouteInfo(
                path="app/api/orders/route.ts",
                endpoint="/orders",
                methods=["POST"],
                is_new=True,
                lines_of_logic=60,
                has_business_logic=True,
                has_tests=True,
            ),
        ]
        missing, _ = analyze_coverage([], routes)
        assert len(missing) == 0

    def test_combined_services_and_routes(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/payment.ts",
                basename="payment",
                is_new=True,
                has_tests=False,
                lines_changed=100,
                contains_financial_logic=True,
            ),
        ]
        routes = [
            APIRouteInfo(
                path="app/api/orders/route.ts",
                endpoint="/orders",
                methods=["POST"],
                is_new=True,
                lines_of_logic=60,
                has_business_logic=True,
            ),
        ]
        missing, summary = analyze_coverage(services, routes)
        assert len(missing) == 2
        assert "2" in summary

    def test_suggested_test_file_format(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/my-service.ts",
                basename="my-service",
                is_new=True,
                has_tests=False,
                lines_changed=100,
            ),
        ]
        missing, _ = analyze_coverage(services, [])
        assert missing[0].suggested_test_file == "tests/lib/services/my-service.test.ts"

    def test_api_route_suggested_test_file(self):
        routes = [
            APIRouteInfo(
                path="app/api/users/route.ts",
                endpoint="/users",
                methods=["GET"],
                is_new=True,
                lines_of_logic=40,
                has_business_logic=True,
            ),
        ]
        missing, _ = analyze_coverage([], routes)
        assert missing[0].suggested_test_file == "tests/app/api/users/route.test.ts"


# ---------------------------------------------------------------------------
# categorize_severity
# ---------------------------------------------------------------------------


class TestCategorizeSeverity:
    """Tests for categorize_severity()."""

    def test_critical_for_critical_service_name(self):
        service = ServiceChangeInfo(
            path="lib/services/receipt-service.ts",
            basename="receipt-service",
            is_new=False,
            has_tests=False,
            lines_changed=10,
        )
        assert categorize_severity(service) == "critical"

    def test_critical_for_directSupplierService(self):
        service = ServiceChangeInfo(
            path="lib/services/directSupplierService.ts",
            basename="directSupplierService",
            is_new=False,
            has_tests=False,
            lines_changed=10,
        )
        assert categorize_severity(service) == "critical"

    def test_critical_for_bale_production_service(self):
        service = ServiceChangeInfo(
            path="lib/services/bale-production-service.ts",
            basename="bale-production-service",
            is_new=False,
            has_tests=False,
            lines_changed=10,
        )
        assert categorize_severity(service) == "critical"

    def test_critical_for_hub_dashboard(self):
        service = ServiceChangeInfo(
            path="lib/services/hub-dashboard.ts",
            basename="hub-dashboard",
            is_new=False,
            has_tests=False,
            lines_changed=10,
        )
        assert categorize_severity(service) == "critical"

    def test_critical_for_financial_logic(self):
        service = ServiceChangeInfo(
            path="lib/services/calculator.ts",
            basename="calculator",
            is_new=False,
            has_tests=False,
            lines_changed=10,
            contains_financial_logic=True,
        )
        assert categorize_severity(service) == "critical"

    def test_high_for_new_service(self):
        service = ServiceChangeInfo(
            path="lib/services/new.ts",
            basename="new",
            is_new=True,
            has_tests=False,
            lines_changed=10,
        )
        assert categorize_severity(service) == "high"

    def test_high_for_many_lines_changed(self):
        service = ServiceChangeInfo(
            path="lib/services/big-refactor.ts",
            basename="big-refactor",
            is_new=False,
            has_tests=False,
            lines_changed=80,
        )
        assert categorize_severity(service) == "high"

    def test_medium_for_small_modified_service(self):
        service = ServiceChangeInfo(
            path="lib/services/small.ts",
            basename="small",
            is_new=False,
            has_tests=False,
            lines_changed=10,
        )
        assert categorize_severity(service) == "medium"

    def test_critical_overrides_high(self):
        """A critical service name should be critical even if new."""
        service = ServiceChangeInfo(
            path="lib/services/receipt-service.ts",
            basename="receipt-service",
            is_new=True,
            has_tests=False,
            lines_changed=200,
            contains_financial_logic=True,
        )
        assert categorize_severity(service) == "critical"

    def test_boundary_at_50_lines(self):
        """Exactly 50 lines changed should be medium, > 50 is high."""
        service_50 = ServiceChangeInfo(
            path="lib/services/border.ts", basename="border", is_new=False, has_tests=False, lines_changed=50
        )
        service_51 = ServiceChangeInfo(
            path="lib/services/border.ts", basename="border", is_new=False, has_tests=False, lines_changed=51
        )
        assert categorize_severity(service_50) == "medium"
        assert categorize_severity(service_51) == "high"


# ---------------------------------------------------------------------------
# should_flag_service
# ---------------------------------------------------------------------------


class TestShouldFlagService:
    """Tests for should_flag_service()."""

    def test_flag_new_service(self):
        service = ServiceChangeInfo(
            path="lib/services/new.ts", basename="new", is_new=True, has_tests=False, lines_changed=5
        )
        assert should_flag_service(service) is True

    def test_flag_financial_logic(self):
        service = ServiceChangeInfo(
            path="lib/services/calc.ts",
            basename="calc",
            is_new=False,
            has_tests=False,
            lines_changed=10,
            contains_financial_logic=True,
        )
        assert should_flag_service(service) is True

    def test_flag_many_lines_changed(self):
        service = ServiceChangeInfo(
            path="lib/services/big.ts", basename="big", is_new=False, has_tests=False, lines_changed=60
        )
        assert should_flag_service(service) is True

    def test_no_flag_small_modified_service(self):
        service = ServiceChangeInfo(
            path="lib/services/tiny.ts", basename="tiny", is_new=False, has_tests=False, lines_changed=10
        )
        assert should_flag_service(service) is False

    def test_boundary_at_50_lines(self):
        service_50 = ServiceChangeInfo(
            path="lib/services/b.ts", basename="b", is_new=False, has_tests=False, lines_changed=50
        )
        service_51 = ServiceChangeInfo(
            path="lib/services/b.ts", basename="b", is_new=False, has_tests=False, lines_changed=51
        )
        assert should_flag_service(service_50) is False
        assert should_flag_service(service_51) is True

    def test_has_tests_does_not_affect_flagging(self):
        """should_flag_service doesn't care about has_tests (that's checked upstream)."""
        service = ServiceChangeInfo(
            path="lib/services/x.ts", basename="x", is_new=True, has_tests=True, lines_changed=5
        )
        assert should_flag_service(service) is True


# ---------------------------------------------------------------------------
# generate_test_recommendations
# ---------------------------------------------------------------------------


class TestGenerateTestRecommendations:
    """Tests for generate_test_recommendations()."""

    def test_financial_logic_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/pricing.ts",
            basename="pricing",
            is_new=True,
            has_tests=False,
            lines_changed=100,
            contains_financial_logic=True,
        )
        recs = generate_test_recommendations(service)
        assert any("decimal precision" in r.lower() for r in recs)
        assert any("zero" in r.lower() or "negative" in r.lower() for r in recs)
        assert any("accuracy" in r.lower() for r in recs)

    def test_payment_service_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/payment-service.ts",
            basename="payment-service",
            is_new=True,
            has_tests=False,
            lines_changed=100,
        )
        recs = generate_test_recommendations(service)
        assert any("payment" in r.lower() for r in recs)
        assert any("aggregation" in r.lower() for r in recs)
        assert any("status" in r.lower() for r in recs)

    def test_supplier_service_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/supplier-utils.ts",
            basename="supplier-utils",
            is_new=True,
            has_tests=False,
            lines_changed=50,
        )
        recs = generate_test_recommendations(service)
        assert any("payment" in r.lower() for r in recs)

    def test_csv_in_basename_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/csv-export.ts",
            basename="csv-export",
            is_new=True,
            has_tests=False,
            lines_changed=50,
            content="export function toCSV() {}",
        )
        recs = generate_test_recommendations(service)
        assert any("csv" in r.lower() for r in recs)

    def test_csv_in_content_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/data-export.ts",
            basename="data-export",
            is_new=True,
            has_tests=False,
            lines_changed=50,
            content="function exportToCSV(data) { /* csv generation */ }",
        )
        recs = generate_test_recommendations(service)
        assert any("csv" in r.lower() for r in recs)

    def test_aggregate_content_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/report-service.ts",
            basename="report-service",
            is_new=True,
            has_tests=False,
            lines_changed=80,
            content="function aggregate(items) { return items.group(); }",
        )
        recs = generate_test_recommendations(service)
        assert any("grouping" in r.lower() for r in recs)
        assert any("aggregation" in r.lower() or "empty" in r.lower() for r in recs)

    def test_group_content_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/data-service.ts",
            basename="data-service",
            is_new=True,
            has_tests=False,
            lines_changed=50,
            content="function groupByCategory(items) {}",
        )
        recs = generate_test_recommendations(service)
        assert any("grouping" in r.lower() for r in recs)

    def test_always_includes_generic_recommendations(self):
        service = ServiceChangeInfo(
            path="lib/services/plain.ts",
            basename="plain",
            is_new=True,
            has_tests=False,
            lines_changed=20,
        )
        recs = generate_test_recommendations(service)
        assert any("happy path" in r.lower() for r in recs)
        assert any("error handling" in r.lower() for r in recs)

    def test_plain_service_only_generic(self):
        """A service with no special keywords should get only generic recommendations."""
        service = ServiceChangeInfo(
            path="lib/services/auth.ts",
            basename="auth",
            is_new=False,
            has_tests=False,
            lines_changed=20,
            content="function login() {}",
        )
        recs = generate_test_recommendations(service)
        # Should have exactly the two generic recommendations
        assert len(recs) == 2
        assert "Test happy path scenarios" in recs
        assert "Test error handling" in recs


# ---------------------------------------------------------------------------
# generate_summary
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    """Tests for generate_summary()."""

    def test_no_missing_tests(self):
        summary = generate_summary([])
        assert "All services" in summary

    def test_single_critical(self):
        missing = [
            MissingTest(
                service_file="lib/services/payment.ts",
                reason="critical_logic_no_test",
                severity="critical",
                suggested_test_file="tests/lib/services/payment.test.ts",
            ),
        ]
        summary = generate_summary(missing)
        assert "1 item(s)" in summary
        assert "1 critical" in summary

    def test_single_high(self):
        missing = [
            MissingTest(
                service_file="lib/services/new.ts",
                reason="new_service_no_test",
                severity="high",
                suggested_test_file="tests/lib/services/new.test.ts",
            ),
        ]
        summary = generate_summary(missing)
        assert "1 high priority" in summary

    def test_single_medium(self):
        missing = [
            MissingTest(
                service_file="lib/services/old.ts",
                reason="modified_service_no_test",
                severity="medium",
                suggested_test_file="tests/lib/services/old.test.ts",
            ),
        ]
        summary = generate_summary(missing)
        assert "1 medium priority" in summary

    def test_mixed_severities(self):
        missing = [
            MissingTest(service_file="a.ts", reason="critical_logic_no_test", severity="critical", suggested_test_file="t.ts"),
            MissingTest(service_file="b.ts", reason="new_service_no_test", severity="high", suggested_test_file="t.ts"),
            MissingTest(service_file="c.ts", reason="modified_service_no_test", severity="medium", suggested_test_file="t.ts"),
            MissingTest(service_file="d.ts", reason="new_service_no_test", severity="high", suggested_test_file="t.ts"),
        ]
        summary = generate_summary(missing)
        assert "4 item(s)" in summary
        assert "1 critical" in summary
        assert "2 high priority" in summary
        assert "1 medium priority" in summary

    def test_summary_does_not_include_absent_levels(self):
        missing = [
            MissingTest(service_file="a.ts", reason="new_service_no_test", severity="high", suggested_test_file="t.ts"),
        ]
        summary = generate_summary(missing)
        assert "critical" not in summary
        assert "medium" not in summary
