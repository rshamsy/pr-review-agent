"""Test coverage analyzer — ported from test-coverage.ts.

Detects test gaps and generates recommendations.
"""

from __future__ import annotations

from pr_review_agent.models.pr import APIRouteInfo, ServiceChangeInfo
from pr_review_agent.models.review import MissingTest

CRITICAL_SERVICES = [
    "directSupplierService",
    "receipt-service",
    "bale-production-service",
    "hub-dashboard",
]


def analyze_coverage(
    services: list[ServiceChangeInfo],
    api_routes: list[APIRouteInfo],
) -> tuple[list[MissingTest], str]:
    """Analyze test coverage gaps. Returns (missing_tests, summary)."""
    missing: list[MissingTest] = []

    for service in services:
        if service.has_tests:
            continue

        severity = categorize_severity(service)
        if service.is_new:
            reason = "new_service_no_test"
        elif service.contains_financial_logic:
            reason = "critical_logic_no_test"
        else:
            reason = "modified_service_no_test"

        if should_flag_service(service):
            missing.append(MissingTest(
                service_file=service.path,
                reason=reason,
                severity=severity,
                suggested_test_file=f"tests/lib/services/{service.basename}.test.ts",
            ))

    for route in api_routes:
        if route.has_tests:
            continue
        if not route.has_business_logic:
            continue
        if route.lines_of_logic < 30:
            continue

        missing.append(MissingTest(
            service_file=route.path,
            reason="api_route_no_test",
            severity="high" if route.lines_of_logic > 50 else "medium",
            suggested_test_file=f"tests/{route.path.rsplit('.', 1)[0]}.test.ts",
        ))

    summary = generate_summary(missing)
    return missing, summary


def categorize_severity(service: ServiceChangeInfo) -> str:
    """Categorize the severity of a missing test."""
    if service.basename in CRITICAL_SERVICES:
        return "critical"
    if service.contains_financial_logic:
        return "critical"
    if service.is_new:
        return "high"
    if service.lines_changed > 50:
        return "high"
    return "medium"


def should_flag_service(service: ServiceChangeInfo) -> bool:
    """Determine if a service should be flagged for missing tests."""
    if service.is_new:
        return True
    if service.contains_financial_logic:
        return True
    if service.lines_changed > 50:
        return True
    return False


def generate_summary(missing: list[MissingTest]) -> str:
    """Generate a human-readable summary of missing tests."""
    if not missing:
        return "All services and API routes have appropriate test coverage"

    critical = [m for m in missing if m.severity == "critical"]
    high = [m for m in missing if m.severity == "high"]
    medium = [m for m in missing if m.severity == "medium"]

    summary = f"Found {len(missing)} item(s) without tests:\n"
    if critical:
        summary += f"  {len(critical)} critical\n"
    if high:
        summary += f"  {len(high)} high priority\n"
    if medium:
        summary += f"  {len(medium)} medium priority\n"

    return summary


def generate_test_recommendations(service: ServiceChangeInfo) -> list[str]:
    """Generate test recommendations for a service."""
    recommendations: list[str] = []

    if service.contains_financial_logic:
        recommendations.append("Test price calculations with decimal precision")
        recommendations.append("Test edge cases: zero, negative, null values")
        recommendations.append("Test calculation accuracy with various inputs")

    if "payment" in service.basename or "supplier" in service.basename:
        recommendations.append("Test payment creation and validation")
        recommendations.append("Test aggregation logic")
        recommendations.append("Test status transitions")

    if "csv" in service.basename or "csv" in service.content.lower():
        recommendations.append("Test CSV export format")
        recommendations.append("Test data accuracy in exported CSV")

    if "aggregate" in service.content.lower() or "group" in service.content.lower():
        recommendations.append("Test data grouping logic")
        recommendations.append("Test aggregation with empty results")

    # Generic recommendations
    recommendations.append("Test happy path scenarios")
    recommendations.append("Test error handling")

    return recommendations
