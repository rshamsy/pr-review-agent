"""Tests for the PR analyzer module."""

from __future__ import annotations

import pytest

from pr_review_agent.analyzers.pr_analyzer import (
    analyze_pr,
    assess_risks,
    classify_pr,
    detect_api_routes,
    detect_service_changes,
    detect_test_files,
    detect_ui_changes,
    find_missing_tests,
)
from pr_review_agent.models.pr import (
    APIRouteInfo,
    FileChange,
    PRAnalysis,
    PRData,
    ServiceChangeInfo,
    TestFileInfo,
    UIChangeInfo,
)
from pr_review_agent.models.review import MissingTest, Risk


# ---------------------------------------------------------------------------
# detect_service_changes
# ---------------------------------------------------------------------------


class TestDetectServiceChanges:
    """Tests for detect_service_changes()."""

    def test_detects_lib_services_ts(self):
        files = [
            FileChange(
                filename="lib/services/payment-service.ts",
                status="added",
                additions=100,
                deletions=0,
                patch="+export function calculatePayment(amount: number, price: number) {}",
            ),
        ]
        services = detect_service_changes(files)
        assert len(services) == 1
        assert services[0].path == "lib/services/payment-service.ts"
        assert services[0].basename == "payment-service"
        assert services[0].is_new is True
        assert services[0].lines_changed == 100
        assert services[0].contains_financial_logic is True  # "price" keyword

    def test_detects_src_services_js(self):
        files = [
            FileChange(
                filename="src/services/user-service.js",
                status="modified",
                additions=10,
                deletions=5,
                patch="+function getUser() {}",
            ),
        ]
        services = detect_service_changes(files)
        assert len(services) == 1
        assert services[0].basename == "user-service"
        assert services[0].is_new is False

    def test_detects_python_service(self):
        files = [
            FileChange(
                filename="services/order_processor.py",
                status="modified",
                additions=20,
                deletions=3,
                patch="+def process_order(): pass",
            ),
        ]
        services = detect_service_changes(files)
        assert len(services) == 1
        assert services[0].basename == "order_processor"

    def test_ignores_non_service_files(self):
        files = [
            FileChange(filename="components/Header.tsx", status="modified", additions=5, patch="+jsx"),
            FileChange(filename="app/api/route.ts", status="added", additions=10, patch="+handler"),
            FileChange(filename="prisma/schema.prisma", status="modified", additions=3, patch="+model"),
        ]
        services = detect_service_changes(files)
        assert len(services) == 0

    def test_financial_keyword_detection(self):
        keywords_and_patches = [
            ("price", "+const price = 10;"),
            ("payment", "+function handlePayment() {}"),
            ("cost", "+const totalCost = 0;"),
            ("total", "+calculateTotal()"),
            ("calculate", "+calculate()"),
            ("balance", "+getBalance()"),
            ("amount", "+const amount = 5;"),
        ]
        for keyword, patch in keywords_and_patches:
            files = [FileChange(filename="lib/services/svc.ts", status="modified", additions=5, patch=patch)]
            services = detect_service_changes(files)
            assert services[0].contains_financial_logic is True, f"Failed for keyword: {keyword}"

    def test_no_financial_keyword(self):
        files = [
            FileChange(
                filename="lib/services/auth-service.ts",
                status="modified",
                additions=10,
                patch="+function authenticate(user) {}",
            ),
        ]
        services = detect_service_changes(files)
        assert services[0].contains_financial_logic is False

    def test_has_tests_true_when_test_present(self):
        files = [
            FileChange(filename="lib/services/user-service.ts", status="modified", additions=10, patch="+code"),
            FileChange(filename="tests/lib/services/user-service.test.ts", status="added", additions=20, patch="+test"),
        ]
        services = detect_service_changes(files)
        # The test file path also matches services/ pattern, so both are detected.
        # The actual service file should have has_tests=True.
        actual_service = [s for s in services if s.path == "lib/services/user-service.ts"]
        assert len(actual_service) == 1
        assert actual_service[0].has_tests is True

    def test_has_tests_false_when_no_test(self):
        files = [
            FileChange(filename="lib/services/user-service.ts", status="modified", additions=10, patch="+code"),
        ]
        services = detect_service_changes(files)
        assert len(services) == 1
        assert services[0].has_tests is False

    def test_multiple_services(self):
        files = [
            FileChange(filename="lib/services/payment-service.ts", status="added", additions=100, patch="+payment"),
            FileChange(filename="lib/services/auth-service.ts", status="modified", additions=20, patch="+auth"),
        ]
        services = detect_service_changes(files)
        assert len(services) == 2
        basenames = {s.basename for s in services}
        assert basenames == {"payment-service", "auth-service"}


# ---------------------------------------------------------------------------
# detect_api_routes
# ---------------------------------------------------------------------------


class TestDetectAPIRoutes:
    """Tests for detect_api_routes()."""

    def test_detects_nextjs_api_route(self):
        files = [
            FileChange(
                filename="app/api/users/route.ts",
                status="added",
                additions=50,
                patch="+export async function GET(request: Request) {\n+  return Response.json({});\n+}",
            ),
        ]
        routes = detect_api_routes(files)
        assert len(routes) == 1
        assert routes[0].endpoint == "/users"
        assert routes[0].is_new is True
        assert "GET" in routes[0].methods

    def test_detects_multiple_methods(self):
        files = [
            FileChange(
                filename="app/api/orders/route.ts",
                status="added",
                additions=100,
                patch=(
                    "+export async function GET(req: Request) {}\n"
                    "+export async function POST(req: Request) {\n"
                    "+  if (!valid) throw new Error('Invalid');\n"
                    "+}"
                ),
            ),
        ]
        routes = detect_api_routes(files)
        assert len(routes) == 1
        assert set(routes[0].methods) == {"GET", "POST"}

    def test_detects_pages_api_route(self):
        files = [
            FileChange(
                filename="pages/api/auth.ts",
                status="modified",
                additions=15,
                patch="+export default function handler() {}",
            ),
        ]
        routes = detect_api_routes(files)
        assert len(routes) == 1

    def test_business_logic_detection_from_lines(self):
        """Routes with > 30 lines of logic are flagged as having business logic."""
        files = [
            FileChange(
                filename="app/api/reports/route.ts",
                status="added",
                additions=35,
                patch="+export async function GET(req: Request) { /* lots of logic */ }",
            ),
        ]
        routes = detect_api_routes(files)
        assert routes[0].has_business_logic is True

    def test_business_logic_detection_from_financial_keywords(self):
        files = [
            FileChange(
                filename="app/api/payments/route.ts",
                status="added",
                additions=10,
                patch="+export async function POST(req: Request) {\n+  const total = calculateTotal();\n+}",
            ),
        ]
        routes = detect_api_routes(files)
        assert routes[0].has_business_logic is True

    def test_business_logic_detection_from_throw(self):
        files = [
            FileChange(
                filename="app/api/orders/route.ts",
                status="added",
                additions=10,
                patch="+if (invalid) throw new Error('bad');\n+export async function POST(req: Request) {}",
            ),
        ]
        routes = detect_api_routes(files)
        assert routes[0].has_business_logic is True

    def test_no_business_logic_for_simple_route(self):
        files = [
            FileChange(
                filename="app/api/health/route.ts",
                status="added",
                additions=5,
                patch="+export async function GET() { return ok; }",
            ),
        ]
        routes = detect_api_routes(files)
        assert routes[0].has_business_logic is False

    def test_ignores_non_api_files(self):
        files = [
            FileChange(filename="lib/services/payment-service.ts", status="added", additions=50, patch="+code"),
            FileChange(filename="components/Button.tsx", status="added", additions=10, patch="+jsx"),
        ]
        routes = detect_api_routes(files)
        assert len(routes) == 0

    def test_endpoint_extraction_nested(self):
        files = [
            FileChange(
                filename="app/api/v1/users/[id]/route.ts",
                status="added",
                additions=10,
                patch="+export async function GET() {}",
            ),
        ]
        routes = detect_api_routes(files)
        assert routes[0].endpoint == "/v1/users/[id]"

    def test_multiple_api_routes(self):
        files = [
            FileChange(filename="app/api/users/route.ts", status="added", additions=10, patch="+export async function GET() {}"),
            FileChange(filename="app/api/orders/route.ts", status="added", additions=15, patch="+export async function POST() {}"),
        ]
        routes = detect_api_routes(files)
        assert len(routes) == 2
        endpoints = {r.endpoint for r in routes}
        assert endpoints == {"/users", "/orders"}

    def test_has_tests_true_when_test_in_pr(self):
        """Route is marked has_tests=True when a matching test file exists in the PR."""
        files = [
            FileChange(filename="app/api/auth/verify-otp/route.ts", status="added", additions=60, patch="+logic"),
            FileChange(filename="tests/lib/services/verify-otp.route.test.ts", status="added", additions=40, patch="+test"),
        ]
        routes = detect_api_routes(files)
        assert len(routes) == 1
        assert routes[0].has_tests is True

    def test_has_tests_false_when_no_matching_test(self):
        files = [
            FileChange(filename="app/api/auth/verify-otp/route.ts", status="added", additions=60, patch="+logic"),
        ]
        routes = detect_api_routes(files)
        assert len(routes) == 1
        assert routes[0].has_tests is False

    def test_has_tests_matches_by_directory_name(self):
        """Test matching uses the parent directory name, not the filename 'route'."""
        files = [
            FileChange(filename="app/api/payments/route.ts", status="added", additions=40, patch="+code"),
            FileChange(filename="tests/api/payments.test.ts", status="added", additions=20, patch="+test"),
        ]
        routes = detect_api_routes(files)
        assert routes[0].has_tests is True


# ---------------------------------------------------------------------------
# detect_ui_changes
# ---------------------------------------------------------------------------


class TestDetectUIChanges:
    """Tests for detect_ui_changes()."""

    def test_detects_page(self):
        files = [
            FileChange(
                filename="app/dashboard/page.tsx",
                status="added",
                additions=50,
                patch="+export default function DashboardPage() {}",
            ),
        ]
        changes = detect_ui_changes(files)
        assert len(changes) == 1
        assert changes[0].type == "page"
        assert changes[0].is_new is True

    def test_detects_component(self):
        files = [
            FileChange(
                filename="components/PaymentTable.tsx",
                status="modified",
                additions=20,
                deletions=5,
                patch="+export function PaymentTable() {}",
            ),
        ]
        changes = detect_ui_changes(files)
        assert len(changes) == 1
        assert changes[0].type == "component"
        assert changes[0].is_new is False

    def test_detects_src_component(self):
        files = [
            FileChange(
                filename="src/components/Modal.tsx",
                status="added",
                additions=30,
                patch="+export function Modal() {}",
            ),
        ]
        changes = detect_ui_changes(files)
        assert len(changes) == 1
        assert changes[0].type == "component"

    def test_detects_state_with_usestate(self):
        files = [
            FileChange(
                filename="components/Counter.tsx",
                status="added",
                additions=10,
                patch="+import { useState } from 'react';\n+const [count, setCount] = useState(0);",
            ),
        ]
        changes = detect_ui_changes(files)
        assert changes[0].has_state is True

    def test_detects_state_with_usereducer(self):
        files = [
            FileChange(
                filename="components/Form.tsx",
                status="added",
                additions=15,
                patch="+import { useReducer } from 'react';\n+const [state, dispatch] = useReducer(reducer, init);",
            ),
        ]
        changes = detect_ui_changes(files)
        assert changes[0].has_state is True

    def test_detects_effects(self):
        files = [
            FileChange(
                filename="app/dashboard/page.tsx",
                status="added",
                additions=20,
                patch="+import { useEffect } from 'react';\n+useEffect(() => { fetch(); }, []);",
            ),
        ]
        changes = detect_ui_changes(files)
        assert changes[0].has_effects is True

    def test_no_state_or_effects(self):
        files = [
            FileChange(
                filename="components/StaticBanner.tsx",
                status="added",
                additions=5,
                patch="+export function Banner() { return <div>Hello</div>; }",
            ),
        ]
        changes = detect_ui_changes(files)
        assert changes[0].has_state is False
        assert changes[0].has_effects is False

    def test_lines_changed_calculation(self):
        files = [
            FileChange(
                filename="components/Table.tsx",
                status="modified",
                additions=30,
                deletions=10,
                patch="+code",
            ),
        ]
        changes = detect_ui_changes(files)
        assert changes[0].lines_changed == 40

    def test_ignores_non_ui_files(self):
        files = [
            FileChange(filename="lib/services/user-service.ts", status="modified", additions=10, patch="+code"),
            FileChange(filename="app/api/route.ts", status="added", additions=5, patch="+handler"),
        ]
        changes = detect_ui_changes(files)
        assert len(changes) == 0

    def test_multiple_ui_changes(self):
        files = [
            FileChange(filename="app/settings/page.tsx", status="added", additions=40, patch="+page"),
            FileChange(filename="components/SettingsForm.tsx", status="added", additions=60, patch="+component"),
        ]
        changes = detect_ui_changes(files)
        assert len(changes) == 2
        types = {c.type for c in changes}
        assert types == {"page", "component"}


# ---------------------------------------------------------------------------
# detect_test_files
# ---------------------------------------------------------------------------


class TestDetectTestFiles:
    """Tests for detect_test_files()."""

    def test_detects_test_ts(self):
        files = [
            FileChange(filename="tests/lib/services/payment-service.test.ts", status="added", additions=50, patch="+test"),
        ]
        tests = detect_test_files(files)
        assert len(tests) == 1
        assert tests[0].path == "tests/lib/services/payment-service.test.ts"
        assert tests[0].tested_file == "lib/services/payment-service.ts"

    def test_detects_spec_js(self):
        files = [
            FileChange(filename="test/utils/helpers.spec.js", status="added", additions=20, patch="+test"),
        ]
        tests = detect_test_files(files)
        assert len(tests) == 1
        assert tests[0].tested_file == "utils/helpers.js"

    def test_detects_dunder_tests(self):
        files = [
            FileChange(filename="__tests__/component.tsx", status="added", additions=10, patch="+test"),
        ]
        tests = detect_test_files(files)
        assert len(tests) == 1
        assert tests[0].tested_file == "component.tsx"

    def test_detects_python_test(self):
        files = [
            FileChange(filename="tests/test_service.test.py", status="added", additions=30, patch="+test"),
        ]
        tests = detect_test_files(files)
        assert len(tests) == 1

    def test_ignores_non_test_files(self):
        files = [
            FileChange(filename="lib/services/user-service.ts", status="modified", additions=10, patch="+code"),
            FileChange(filename="components/Button.tsx", status="added", additions=5, patch="+jsx"),
        ]
        tests = detect_test_files(files)
        assert len(tests) == 0

    def test_multiple_test_files(self):
        files = [
            FileChange(filename="tests/lib/services/auth.test.ts", status="added", additions=20, patch="+t"),
            FileChange(filename="tests/lib/services/payment.test.ts", status="added", additions=30, patch="+t"),
        ]
        tests = detect_test_files(files)
        assert len(tests) == 2

    def test_maps_tested_file_correctly(self):
        """Ensure the tested_file mapping strips test/spec and prefix."""
        files = [
            FileChange(filename="tests/lib/services/order-service.spec.ts", status="added", additions=10, patch="+t"),
        ]
        tests = detect_test_files(files)
        assert tests[0].tested_file == "lib/services/order-service.ts"


# ---------------------------------------------------------------------------
# find_missing_tests
# ---------------------------------------------------------------------------


class TestFindMissingTests:
    """Tests for find_missing_tests()."""

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
        missing = find_missing_tests(services, [], [])
        assert len(missing) == 1
        assert missing[0].reason == "new_service_no_test"
        assert missing[0].severity == "high"

    def test_does_not_flag_service_with_tests(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/existing.ts",
                basename="existing",
                is_new=False,
                has_tests=True,
                lines_changed=200,
            ),
        ]
        missing = find_missing_tests(services, [], [])
        assert len(missing) == 0

    def test_flags_critical_for_financial_logic(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/payment-service.ts",
                basename="payment-service",
                is_new=True,
                has_tests=False,
                lines_changed=100,
                contains_financial_logic=True,
            ),
        ]
        missing = find_missing_tests(services, [], [])
        assert len(missing) == 1
        assert missing[0].severity == "critical"
        assert missing[0].reason == "critical_logic_no_test"

    def test_flags_critical_for_critical_service_name(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/receipt-service.ts",
                basename="receipt-service",
                is_new=True,
                has_tests=False,
                lines_changed=100,
            ),
        ]
        missing = find_missing_tests(services, [], [])
        assert len(missing) == 1
        assert missing[0].severity == "critical"

    def test_does_not_flag_small_modified_service(self):
        """Modified service with few lines changed should not be flagged."""
        services = [
            ServiceChangeInfo(
                path="lib/services/small-change.ts",
                basename="small-change",
                is_new=False,
                has_tests=False,
                lines_changed=10,
            ),
        ]
        missing = find_missing_tests(services, [], [])
        assert len(missing) == 0

    def test_flags_large_modified_service(self):
        """Modified service with >50 lines changed should be flagged."""
        services = [
            ServiceChangeInfo(
                path="lib/services/big-refactor.ts",
                basename="big-refactor",
                is_new=False,
                has_tests=False,
                lines_changed=80,
            ),
        ]
        missing = find_missing_tests(services, [], [])
        assert len(missing) == 1
        assert missing[0].reason == "modified_service_no_test"

    def test_flags_api_route_with_business_logic(self):
        routes = [
            APIRouteInfo(
                path="app/api/payments/route.ts",
                endpoint="/payments",
                methods=["POST"],
                is_new=True,
                lines_of_logic=60,
                has_business_logic=True,
            ),
        ]
        missing = find_missing_tests([], routes, [])
        assert len(missing) == 1
        assert missing[0].reason == "api_route_no_test"
        assert missing[0].severity == "high"  # lines_of_logic > 50

    def test_does_not_flag_api_route_with_tests(self):
        """API route with has_tests=True should not be flagged as missing tests."""
        routes = [
            APIRouteInfo(
                path="app/api/auth/verify-otp/route.ts",
                endpoint="/auth/verify-otp",
                methods=["POST"],
                is_new=True,
                lines_of_logic=60,
                has_business_logic=True,
                has_tests=True,
            ),
        ]
        missing = find_missing_tests([], routes, [])
        assert len(missing) == 0

    def test_does_not_flag_api_route_without_business_logic(self):
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
        missing = find_missing_tests([], routes, [])
        assert len(missing) == 0

    def test_api_route_medium_severity_for_fewer_lines(self):
        routes = [
            APIRouteInfo(
                path="app/api/items/route.ts",
                endpoint="/items",
                methods=["GET"],
                is_new=True,
                lines_of_logic=40,
                has_business_logic=True,
            ),
        ]
        missing = find_missing_tests([], routes, [])
        assert len(missing) == 1
        assert missing[0].severity == "medium"

    def test_suggested_test_file_for_service(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/order-service.ts",
                basename="order-service",
                is_new=True,
                has_tests=False,
                lines_changed=100,
            ),
        ]
        missing = find_missing_tests(services, [], [])
        assert missing[0].suggested_test_file == "tests/lib/services/order-service.test.ts"


# ---------------------------------------------------------------------------
# assess_risks
# ---------------------------------------------------------------------------


class TestAssessRisks:
    """Tests for assess_risks()."""

    def test_critical_risk_for_financial_logic_no_tests(self):
        missing = [
            MissingTest(
                service_file="lib/services/payment.ts",
                reason="critical_logic_no_test",
                severity="critical",
                suggested_test_file="tests/lib/services/payment.test.ts",
            ),
        ]
        risks = assess_risks([], [], missing)
        assert any(r.level == "critical" for r in risks)
        assert any(r.category == "test-coverage" for r in risks)

    def test_high_risk_for_new_service_no_tests(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/new-svc.ts",
                basename="new-svc",
                is_new=True,
                has_tests=False,
                lines_changed=50,
            ),
        ]
        risks = assess_risks(services, [], [])
        assert any(r.level == "high" for r in risks)

    def test_medium_risk_for_api_business_logic(self):
        routes = [
            APIRouteInfo(
                path="app/api/orders/route.ts",
                endpoint="/orders",
                methods=["POST"],
                is_new=True,
                lines_of_logic=50,
                has_business_logic=True,
            ),
        ]
        risks = assess_risks([], routes, [])
        assert any(r.level == "medium" for r in risks)
        assert any(r.category == "business-logic" for r in risks)

    def test_no_risks_when_all_clean(self):
        services = [
            ServiceChangeInfo(
                path="lib/services/safe.ts",
                basename="safe",
                is_new=False,
                has_tests=True,
                lines_changed=10,
            ),
        ]
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
        risks = assess_risks(services, routes, [])
        assert len(risks) == 0

    def test_multiple_risks_combined(self):
        services = [
            ServiceChangeInfo(path="lib/services/new.ts", basename="new", is_new=True, has_tests=False, lines_changed=50),
        ]
        routes = [
            APIRouteInfo(path="app/api/orders/route.ts", endpoint="/orders", methods=["POST"], is_new=True, lines_of_logic=50, has_business_logic=True),
        ]
        missing = [
            MissingTest(service_file="lib/services/pay.ts", reason="critical_logic_no_test", severity="critical", suggested_test_file="t.ts"),
        ]
        risks = assess_risks(services, routes, missing)
        assert len(risks) >= 3  # critical + high + medium


# ---------------------------------------------------------------------------
# classify_pr
# ---------------------------------------------------------------------------


class TestClassifyPR:
    """Tests for classify_pr()."""

    def test_major_for_critical_risk(self):
        pr_data = PRData(number=1, title="x", author="a", additions=10, deletions=0)
        risks = [Risk(level="critical", category="test-coverage", description="critical issue")]
        result = classify_pr(pr_data, [], risks)
        assert result == "major"

    def test_major_for_new_service_without_tests(self):
        pr_data = PRData(number=1, title="x", author="a", additions=10, deletions=0)
        services = [
            ServiceChangeInfo(path="lib/services/new.ts", basename="new", is_new=True, has_tests=False, lines_changed=50),
        ]
        result = classify_pr(pr_data, services, [])
        assert result == "major"

    def test_major_for_large_pr(self):
        pr_data = PRData(number=1, title="x", author="a", additions=400, deletions=200)
        result = classify_pr(pr_data, [], [])
        assert result == "major"

    def test_major_for_financial_logic_with_many_changes(self):
        pr_data = PRData(number=1, title="x", author="a", additions=30, deletions=30)
        services = [
            ServiceChangeInfo(
                path="lib/services/pay.ts",
                basename="pay",
                is_new=False,
                has_tests=True,
                lines_changed=60,
                contains_financial_logic=True,
            ),
        ]
        result = classify_pr(pr_data, services, [])
        assert result == "major"

    def test_minor_for_moderate_lines(self):
        pr_data = PRData(number=1, title="x", author="a", additions=80, deletions=30)
        result = classify_pr(pr_data, [], [])
        assert result == "minor"

    def test_minor_when_services_present(self):
        pr_data = PRData(number=1, title="x", author="a", additions=10, deletions=5)
        services = [
            ServiceChangeInfo(path="lib/services/svc.ts", basename="svc", is_new=False, has_tests=True, lines_changed=10),
        ]
        result = classify_pr(pr_data, services, [])
        assert result == "minor"

    def test_minor_when_risks_present(self):
        pr_data = PRData(number=1, title="x", author="a", additions=10, deletions=5)
        risks = [Risk(level="medium", category="business-logic", description="medium issue")]
        result = classify_pr(pr_data, [], risks)
        assert result == "minor"

    def test_trivial_for_small_clean_pr(self):
        pr_data = PRData(number=1, title="fix typo", author="a", additions=3, deletions=2)
        result = classify_pr(pr_data, [], [])
        assert result == "trivial"

    def test_trivial_boundary_at_100(self):
        """Exactly 100 total lines should be trivial (> 100 triggers minor)."""
        pr_data = PRData(number=1, title="x", author="a", additions=50, deletions=50)
        result = classify_pr(pr_data, [], [])
        assert result == "trivial"

    def test_minor_boundary_at_101(self):
        pr_data = PRData(number=1, title="x", author="a", additions=51, deletions=50)
        result = classify_pr(pr_data, [], [])
        assert result == "minor"


# ---------------------------------------------------------------------------
# analyze_pr (end-to-end)
# ---------------------------------------------------------------------------


class TestAnalyzePR:
    """Tests for analyze_pr() end-to-end."""

    def test_end_to_end_with_sample_data(self, sample_pr_data: PRData):
        analysis = analyze_pr(sample_pr_data)

        assert isinstance(analysis, PRAnalysis)
        assert analysis.total_additions == 682
        assert analysis.total_deletions == 35
        assert analysis.classification == "major"

        # Should detect services
        assert len(analysis.services) >= 1

        # Should detect API routes
        assert len(analysis.api_routes) >= 1

        # Should detect UI changes
        assert len(analysis.ui_changes) >= 1

        # Should detect test files
        assert len(analysis.test_files) >= 1

    def test_end_to_end_trivial_pr(self):
        pr_data = PRData(
            number=99,
            title="Fix typo in readme",
            author="dev",
            additions=1,
            deletions=1,
            files=[
                FileChange(filename="README.md", status="modified", additions=1, deletions=1, patch="+fixed typo"),
            ],
        )
        analysis = analyze_pr(pr_data)
        assert analysis.classification == "trivial"
        assert len(analysis.services) == 0
        assert len(analysis.api_routes) == 0
        assert len(analysis.ui_changes) == 0

    def test_end_to_end_migrations_not_populated(self):
        """analyze_pr sets migrations to empty; they are filled separately."""
        pr_data = PRData(
            number=10,
            title="Add migration",
            author="dev",
            additions=10,
            deletions=0,
            files=[
                FileChange(
                    filename="prisma/migrations/001/migration.sql",
                    status="added",
                    additions=10,
                    patch='+CREATE TABLE "t" ("id" TEXT);',
                ),
            ],
        )
        analysis = analyze_pr(pr_data)
        assert analysis.migrations == []

    def test_end_to_end_with_service_and_test(self):
        pr_data = PRData(
            number=15,
            title="Update auth",
            author="dev",
            additions=40,
            deletions=10,
            files=[
                FileChange(filename="lib/services/auth-service.ts", status="modified", additions=30, deletions=10, patch="+auth update"),
                FileChange(filename="tests/lib/services/auth-service.test.ts", status="modified", additions=10, deletions=0, patch="+tests"),
            ],
        )
        analysis = analyze_pr(pr_data)
        # The test file also matches the services/ pattern, so 2 services detected
        actual_service = [s for s in analysis.services if s.path == "lib/services/auth-service.ts"]
        assert len(actual_service) == 1
        assert actual_service[0].has_tests is True
        assert len(analysis.missing_tests) == 0

    def test_end_to_end_risk_assessment(self):
        pr_data = PRData(
            number=20,
            title="Add payment feature",
            author="dev",
            additions=200,
            deletions=0,
            files=[
                FileChange(
                    filename="lib/services/payment-calc.ts",
                    status="added",
                    additions=200,
                    patch="+export function calculateTotal(price, qty) { return price * qty; }",
                ),
            ],
        )
        analysis = analyze_pr(pr_data)
        # New service with financial logic, no tests -> critical risk
        assert any(r.level == "critical" for r in analysis.risks)
        assert any(m.severity == "critical" for m in analysis.missing_tests)
