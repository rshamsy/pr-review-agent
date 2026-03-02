"""Testing checklist generator — ported from checklist-generator.ts.

Generates a context-aware browser testing checklist.
Railway-specific checks removed; generic pre-flight checks included.
"""

from __future__ import annotations

from pr_review_agent.models.pr import APIRouteInfo, PRAnalysis, ServiceChangeInfo, UIChangeInfo
from pr_review_agent.models.migration import MigrationInfo
from pr_review_agent.models.review import TestingChecklistItem


def generate_testing_checklist(
    pr_number: int,
    analysis: PRAnalysis,
) -> list[TestingChecklistItem]:
    """Generate a context-aware testing checklist for a PR."""
    checklist: list[TestingChecklistItem] = []

    # Pre-flight checks
    checklist.extend(generate_pre_flight_checks(pr_number))

    # Migration-specific tests
    if analysis.migrations:
        checklist.extend(generate_migration_checks(analysis.migrations))

    # Service-specific tests
    for service in analysis.services:
        checklist.extend(generate_service_tests(service))

    # API route tests
    for route in analysis.api_routes:
        checklist.extend(generate_api_tests(route))

    # UI tests
    for ui in analysis.ui_changes:
        checklist.extend(generate_ui_tests(ui))

    # Edge case tests
    if any(s.contains_financial_logic for s in analysis.services):
        checklist.extend(generate_edge_case_tests())

    # Sort by priority
    priority_order = {"must": 0, "should": 1, "nice-to-have": 2}
    checklist.sort(key=lambda item: priority_order.get(item.priority, 99))

    return checklist


def generate_pre_flight_checks(pr_number: int) -> list[TestingChecklistItem]:
    """Generate generic pre-flight checks."""
    return [
        TestingChecklistItem(
            category="pre-flight",
            description=f"Verify PR #{pr_number} deployment is running",
            priority="must",
        ),
        TestingChecklistItem(
            category="pre-flight",
            description="Verify database connection is healthy",
            priority="must",
        ),
        TestingChecklistItem(
            category="pre-flight",
            description="Confirm environment variables are set correctly",
            priority="must",
        ),
    ]


def generate_migration_checks(migrations: list[MigrationInfo]) -> list[TestingChecklistItem]:
    """Generate migration-related checks."""
    checks: list[TestingChecklistItem] = []

    checks.append(TestingChecklistItem(
        category="data",
        description=f"Verify {len(migrations)} migration(s) ran successfully",
        priority="must",
    ))

    if any(op.type == "CREATE_TABLE" for m in migrations for op in m.operations):
        checks.append(TestingChecklistItem(
            category="data",
            description="Verify new database tables exist",
            priority="should",
        ))

    if any(op.type == "ADD_COLUMN" for m in migrations for op in m.operations):
        checks.append(TestingChecklistItem(
            category="data",
            description="Verify new columns appear in database",
            priority="should",
        ))

    return checks


def generate_service_tests(service: ServiceChangeInfo) -> list[TestingChecklistItem]:
    """Generate service-specific tests."""
    tests: list[TestingChecklistItem] = []

    if "payment" in service.basename or "supplier" in service.basename:
        tests.append(TestingChecklistItem(
            category="calculation",
            description=f"Test {service.basename} calculations are correct",
            priority="must",
        ))

        if "csv" in service.basename or "csv" in service.content.lower():
            tests.append(TestingChecklistItem(
                category="data",
                description="Test CSV export functionality",
                priority="should",
            ))

    if "receipt" in service.basename:
        tests.append(TestingChecklistItem(
            category="calculation",
            description="Verify weight calculations (net good, net reject)",
            priority="must",
        ))

    if "bale" in service.basename:
        tests.append(TestingChecklistItem(
            category="data",
            description="Test bale production creation and tracking",
            priority="must",
        ))

    return tests


def generate_api_tests(route: APIRouteInfo) -> list[TestingChecklistItem]:
    """Generate API route tests."""
    tests: list[TestingChecklistItem] = []

    for method in route.methods:
        tests.append(TestingChecklistItem(
            category="integration",
            description=f"Test {method} {route.endpoint}",
            url=route.endpoint,
            priority="must" if route.has_business_logic else "should",
        ))

    return tests


def generate_ui_tests(ui: UIChangeInfo) -> list[TestingChecklistItem]:
    """Generate UI-related tests."""
    tests: list[TestingChecklistItem] = []

    if ui.is_new:
        url_path = ui.path.replace("app/", "/").replace("/page.tsx", "")
        tests.append(TestingChecklistItem(
            category="ui",
            description=f"Navigate to {url_path}",
            url=url_path,
            priority="must",
        ))

    if ui.has_state:
        tests.append(TestingChecklistItem(
            category="ui",
            description=f"Test interactive features in {ui.type} {ui.path}",
            priority="should",
        ))

    return tests


def generate_edge_case_tests() -> list[TestingChecklistItem]:
    """Generate edge case tests for financial logic."""
    return [
        TestingChecklistItem(
            category="edge-case",
            description="Test with zero/null values in calculations",
            priority="should",
        ),
        TestingChecklistItem(
            category="edge-case",
            description="Test with large dataset (100+ records)",
            priority="nice-to-have",
        ),
        TestingChecklistItem(
            category="edge-case",
            description="Test error handling for invalid inputs",
            priority="should",
        ),
    ]


def format_checklist(checklist: list[TestingChecklistItem]) -> str:
    """Format checklist for display."""
    output = "BROWSER TESTING CHECKLIST\n\n"

    categories: dict[str, list[TestingChecklistItem]] = {
        "PRE-FLIGHT (CRITICAL)": [],
        "MUST TEST": [],
        "SHOULD TEST": [],
        "NICE TO HAVE": [],
    }

    for item in checklist:
        if item.category == "pre-flight":
            categories["PRE-FLIGHT (CRITICAL)"].append(item)
        elif item.priority == "must":
            categories["MUST TEST"].append(item)
        elif item.priority == "should":
            categories["SHOULD TEST"].append(item)
        else:
            categories["NICE TO HAVE"].append(item)

    for title, items in categories.items():
        if not items:
            continue
        output += f"{title}:\n"
        for item in items:
            url = f" ({item.url})" if item.url else ""
            output += f"  [ ] {item.description}{url}\n"
        output += "\n"

    return output
