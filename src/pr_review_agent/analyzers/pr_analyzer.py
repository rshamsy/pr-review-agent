"""PR analyzer — ported from pr-analyzer.ts.

Detects service changes, API routes, UI components, test files.
Uses PR diff patches instead of reading from disk.
Path patterns are configurable to support any tech stack.
"""

from __future__ import annotations

import re

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

FINANCIAL_KEYWORDS = ["price", "payment", "cost", "total", "calculate", "balance", "amount"]
CRITICAL_SERVICES = [
    "receipt-service",
    "bale-production-service",
    "hub-dashboard",
    "directSupplierService",
]

# Configurable path patterns for different tech stacks
SERVICE_PATTERNS = [
    r"lib/services/.*\.(ts|js|py)$",
    r"src/services/.*\.(ts|js|py)$",
    r"app/services/.*\.(py|rb)$",
    r"services/.*\.(ts|js|py)$",
]

API_ROUTE_PATTERNS = [
    r"app/api/.*/route\.(ts|js)$",
    r"pages/api/.*\.(ts|js)$",
    r"src/routes/.*\.(ts|js|py)$",
    r"app/views\.py$",
    r"app/routes.*\.(py|rb)$",
]

UI_PATTERNS = [
    (r"app/.*/page\.tsx$", "page"),
    (r"pages/.*\.(tsx|jsx)$", "page"),
    (r"components/.*\.(tsx|jsx)$", "component"),
    (r"src/components/.*\.(tsx|jsx|vue)$", "component"),
]

TEST_PATTERNS = [
    r"tests?/.*\.(test|spec)\.(ts|js|py)$",
    r"__tests__/.*\.(ts|js|tsx|jsx)$",
    r".*_test\.py$",
    r".*\.test\.(ts|js|tsx|jsx)$",
]


def analyze_pr(pr_data: PRData) -> PRAnalysis:
    """Main PR analysis entry point."""
    services = detect_service_changes(pr_data.files)
    api_routes = detect_api_routes(pr_data.files)
    ui_changes = detect_ui_changes(pr_data.files)
    test_files = detect_test_files(pr_data.files)
    missing_tests = find_missing_tests(services, api_routes, test_files)
    risks = assess_risks(services, api_routes, missing_tests)
    classification = classify_pr(pr_data, services, risks)

    return PRAnalysis(
        classification=classification,
        migrations=[],  # Populated by migration_analyzer
        services=services,
        api_routes=api_routes,
        ui_changes=ui_changes,
        test_files=test_files,
        risks=risks,
        missing_tests=missing_tests,
        total_additions=pr_data.additions,
        total_deletions=pr_data.deletions,
    )


def detect_service_changes(files: list[FileChange]) -> list[ServiceChangeInfo]:
    """Detect changes to service files using configurable patterns."""
    services: list[ServiceChangeInfo] = []

    for file in files:
        if not any(re.search(p, file.filename) for p in SERVICE_PATTERNS):
            continue

        basename = file.filename.split("/")[-1].rsplit(".", 1)[0]
        is_new = file.status == "added"
        lines_changed = file.additions + file.deletions

        # Use patch content instead of reading from disk
        content = file.patch or ""
        contains_financial = any(
            kw in content.lower() for kw in FINANCIAL_KEYWORDS
        )

        # Check if test exists in the PR files
        has_tests = any(
            _is_test_for_service(f.filename, basename) for f in files
        )

        services.append(ServiceChangeInfo(
            path=file.filename,
            basename=basename,
            is_new=is_new,
            has_tests=has_tests,
            lines_changed=lines_changed,
            content=content,
            contains_financial_logic=contains_financial,
        ))

    return services


def _is_test_for_service(test_path: str, service_basename: str) -> bool:
    """Check if a file path is a test for the given service."""
    return any(re.search(p, test_path) for p in TEST_PATTERNS) and service_basename in test_path


def _is_test_for_route(test_path: str, route_path: str) -> bool:
    """Check if a file path is a test for the given API route.

    For routes like ``app/api/auth/verify-otp/route.ts`` the meaningful
    identifier is the parent directory name (``verify-otp``), not the
    filename (``route``).  We also check the full endpoint path segments
    so that ``tests/app/api/auth/verify-otp/route.test.ts`` matches too.
    """
    if not any(re.search(p, test_path) for p in TEST_PATTERNS):
        return False

    # Extract the meaningful identifier: parent directory of route file
    parts = route_path.split("/")
    # For "app/api/auth/verify-otp/route.ts" → identifier = "verify-otp"
    if len(parts) >= 2:
        route_identifier = parts[-2]
    else:
        route_identifier = parts[0]

    return route_identifier in test_path


def detect_api_routes(files: list[FileChange]) -> list[APIRouteInfo]:
    """Detect API route changes."""
    routes: list[APIRouteInfo] = []

    for file in files:
        if not any(re.search(p, file.filename) for p in API_ROUTE_PATTERNS):
            continue

        is_new = file.status == "added"
        lines_of_logic = file.additions
        content = file.patch or ""

        # Extract endpoint from path
        endpoint = _extract_endpoint(file.filename)

        # Detect HTTP methods from patch content
        methods = _detect_http_methods(content)

        # Detect business logic
        has_business_logic = (
            lines_of_logic > 30
            or any(kw in content.lower() for kw in FINANCIAL_KEYWORDS)
            or ("if " in content and "raise" in content)
            or ("if (" in content and "throw" in content)
        )

        # Check if a test exists in the PR files for this route
        has_tests = any(
            _is_test_for_route(f.filename, file.filename) for f in files
        )

        routes.append(APIRouteInfo(
            path=file.filename,
            endpoint=endpoint,
            methods=methods,
            is_new=is_new,
            lines_of_logic=lines_of_logic,
            has_business_logic=has_business_logic,
            has_tests=has_tests,
        ))

    return routes


def _extract_endpoint(filepath: str) -> str:
    """Extract API endpoint from file path."""
    parts = filepath.split("/")
    if "api" in parts:
        api_idx = parts.index("api")
        # Remove last part if it's a file like route.ts
        endpoint_parts = parts[api_idx + 1:]
        if endpoint_parts and "." in endpoint_parts[-1]:
            endpoint_parts = endpoint_parts[:-1]
        return "/" + "/".join(endpoint_parts) if endpoint_parts else "/api"
    return "/" + filepath


def _detect_http_methods(content: str) -> list[str]:
    """Detect HTTP methods from file content."""
    methods = []
    for method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
        if f"export async function {method}" in content or f"def {method.lower()}" in content:
            methods.append(method)
    return methods


def detect_ui_changes(files: list[FileChange]) -> list[UIChangeInfo]:
    """Detect UI component and page changes."""
    changes: list[UIChangeInfo] = []

    for file in files:
        ui_type = None
        for pattern, type_name in UI_PATTERNS:
            if re.search(pattern, file.filename):
                ui_type = type_name
                break

        if ui_type is None:
            continue

        content = file.patch or ""
        changes.append(UIChangeInfo(
            path=file.filename,
            type=ui_type,
            is_new=file.status == "added",
            has_state="useState" in content or "useReducer" in content,
            has_effects="useEffect" in content,
            lines_changed=file.additions + file.deletions,
        ))

    return changes


def detect_test_files(files: list[FileChange]) -> list[TestFileInfo]:
    """Detect test files and map to source files."""
    tests: list[TestFileInfo] = []

    for file in files:
        if not any(re.search(p, file.filename) for p in TEST_PATTERNS):
            continue

        # Map test file to source: tests/lib/services/foo.test.ts → lib/services/foo.ts
        tested_file = file.filename
        tested_file = re.sub(r"^tests?/", "", tested_file)
        tested_file = re.sub(r"\.(test|spec)\.", ".", tested_file)
        tested_file = re.sub(r"^__tests__/", "", tested_file)

        tests.append(TestFileInfo(path=file.filename, tested_file=tested_file))

    return tests


def find_missing_tests(
    services: list[ServiceChangeInfo],
    api_routes: list[APIRouteInfo],
    test_files: list[TestFileInfo],
) -> list[MissingTest]:
    """Find services and routes that should have tests but don't."""
    missing: list[MissingTest] = []

    for service in services:
        if service.has_tests:
            continue

        severity: str = "medium"
        reason: str = "modified_service_no_test"

        if service.is_new:
            reason = "new_service_no_test"
            severity = "high"

        if service.contains_financial_logic or service.basename in CRITICAL_SERVICES:
            severity = "critical"
            reason = "critical_logic_no_test"

        # Only flag if significant changes
        if service.is_new or service.lines_changed > 50 or service.contains_financial_logic:
            missing.append(MissingTest(
                service_file=service.path,
                reason=reason,
                severity=severity,
                suggested_test_file=f"tests/lib/services/{service.basename}.test.ts",
            ))

    for route in api_routes:
        if not route.has_business_logic:
            continue
        if route.has_tests:
            continue

        missing.append(MissingTest(
            service_file=route.path,
            reason="api_route_no_test",
            severity="high" if route.lines_of_logic > 50 else "medium",
            suggested_test_file=f"tests/{route.path.rsplit('.', 1)[0]}.test.ts",
        ))

    return missing


def assess_risks(
    services: list[ServiceChangeInfo],
    api_routes: list[APIRouteInfo],
    missing_tests: list[MissingTest],
) -> list[Risk]:
    """Assess risks based on detected changes."""
    risks: list[Risk] = []

    # Critical: services with financial logic but no tests
    for test in missing_tests:
        if test.severity == "critical":
            risks.append(Risk(
                level="critical",
                category="test-coverage",
                description=f"{test.service_file} has financial logic but no tests",
                file=test.service_file,
            ))

    # High: new services without tests
    for service in services:
        if service.is_new and not service.has_tests:
            risks.append(Risk(
                level="high",
                category="test-coverage",
                description=f"New service {service.path} has no tests",
                file=service.path,
            ))

    # Medium: API routes with business logic
    for route in api_routes:
        if route.has_business_logic:
            risks.append(Risk(
                level="medium",
                category="business-logic",
                description=f"API route {route.endpoint} contains business logic that should be tested",
                file=route.path,
            ))

    return risks


def classify_pr(
    pr_data: PRData,
    services: list[ServiceChangeInfo],
    risks: list[Risk],
) -> str:
    """Classify PR as major, minor, or trivial."""
    total_lines = pr_data.additions + pr_data.deletions

    # Major conditions
    if any(r.level == "critical" for r in risks):
        return "major"
    if any(s.is_new and not s.has_tests for s in services):
        return "major"
    if total_lines > 500:
        return "major"
    if any(s.contains_financial_logic and s.lines_changed > 50 for s in services):
        return "major"

    # Minor conditions
    if total_lines > 100:
        return "minor"
    if services or risks:
        return "minor"

    return "trivial"
