"""Comprehensive tests for all Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# pr.py models
# ---------------------------------------------------------------------------
from pr_review_agent.models.pr import (
    APIRouteInfo,
    CICheck,
    CIStatus,
    FileChange,
    PRAnalysis,
    PRData,
    ServiceChangeInfo,
    TestFileInfo,
    UIChangeInfo,
)

# ---------------------------------------------------------------------------
# migration.py models
# ---------------------------------------------------------------------------
from pr_review_agent.models.migration import MigrationInfo, MigrationOperation

# ---------------------------------------------------------------------------
# review.py models
# ---------------------------------------------------------------------------
from pr_review_agent.models.review import (
    MissingTest,
    ReviewRecommendation,
    Risk,
    TestingChecklistItem,
)

# ---------------------------------------------------------------------------
# notion.py models
# ---------------------------------------------------------------------------
from pr_review_agent.models.notion import NotionContext, NotionSearchResult, RelevanceScore

# ---------------------------------------------------------------------------
# brief.py models
# ---------------------------------------------------------------------------
from pr_review_agent.models.brief import IntentDelta, ReviewBrief


# ===== FileChange =====


class TestFileChange:
    def test_valid_added(self):
        fc = FileChange(filename="src/app.py", status="added")
        assert fc.filename == "src/app.py"
        assert fc.status == "added"
        assert fc.additions == 0
        assert fc.deletions == 0
        assert fc.patch is None

    def test_valid_modified(self):
        fc = FileChange(
            filename="lib/utils.ts",
            status="modified",
            additions=10,
            deletions=3,
            patch="+new line\n-old line",
        )
        assert fc.status == "modified"
        assert fc.additions == 10
        assert fc.deletions == 3
        assert fc.patch == "+new line\n-old line"

    def test_valid_removed(self):
        fc = FileChange(filename="old.py", status="removed", deletions=50)
        assert fc.status == "removed"
        assert fc.deletions == 50

    def test_invalid_status_literal(self):
        with pytest.raises(ValidationError) as exc_info:
            FileChange(filename="x.py", status="renamed")
        assert "status" in str(exc_info.value)

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            FileChange(status="added")  # missing filename
        with pytest.raises(ValidationError):
            FileChange(filename="x.py")  # missing status


# ===== PRData =====


class TestPRData:
    def test_minimal(self):
        pr = PRData(number=1, title="Fix bug", author="alice")
        assert pr.number == 1
        assert pr.title == "Fix bug"
        assert pr.author == "alice"
        assert pr.additions == 0
        assert pr.deletions == 0
        assert pr.files == []
        assert pr.branch == ""

    def test_full(self):
        fc = FileChange(filename="a.py", status="added", additions=5)
        pr = PRData(
            number=42,
            title="Big feature",
            author="bob",
            additions=100,
            deletions=20,
            files=[fc],
            branch="feature/big",
        )
        assert pr.files == [fc]
        assert pr.branch == "feature/big"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            PRData(title="X", author="Y")  # missing number
        with pytest.raises(ValidationError):
            PRData(number=1, author="Y")  # missing title
        with pytest.raises(ValidationError):
            PRData(number=1, title="X")  # missing author

    def test_files_default_factory(self):
        pr1 = PRData(number=1, title="A", author="a")
        pr2 = PRData(number=2, title="B", author="b")
        assert pr1.files is not pr2.files  # separate list instances


# ===== ServiceChangeInfo =====


class TestServiceChangeInfo:
    def test_minimal(self):
        s = ServiceChangeInfo(path="lib/svc.ts", basename="svc")
        assert s.path == "lib/svc.ts"
        assert s.basename == "svc"
        assert s.is_new is False
        assert s.has_tests is False
        assert s.lines_changed == 0
        assert s.content == ""
        assert s.contains_financial_logic is False

    def test_full(self):
        s = ServiceChangeInfo(
            path="lib/payment.ts",
            basename="payment",
            is_new=True,
            has_tests=True,
            lines_changed=150,
            content="function calc()",
            contains_financial_logic=True,
        )
        assert s.is_new is True
        assert s.contains_financial_logic is True

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ServiceChangeInfo(basename="x")  # missing path
        with pytest.raises(ValidationError):
            ServiceChangeInfo(path="x")  # missing basename


# ===== APIRouteInfo =====


class TestAPIRouteInfo:
    def test_minimal(self):
        r = APIRouteInfo(path="app/api/foo/route.ts", endpoint="/foo")
        assert r.methods == []
        assert r.is_new is False
        assert r.lines_of_logic == 0
        assert r.has_business_logic is False

    def test_full(self):
        r = APIRouteInfo(
            path="app/api/bar/route.ts",
            endpoint="/bar",
            methods=["GET", "POST", "DELETE"],
            is_new=True,
            lines_of_logic=80,
            has_business_logic=True,
        )
        assert r.methods == ["GET", "POST", "DELETE"]
        assert r.has_business_logic is True

    def test_methods_default_factory(self):
        r1 = APIRouteInfo(path="a", endpoint="/a")
        r2 = APIRouteInfo(path="b", endpoint="/b")
        assert r1.methods is not r2.methods

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            APIRouteInfo(endpoint="/x")  # missing path
        with pytest.raises(ValidationError):
            APIRouteInfo(path="x")  # missing endpoint


# ===== UIChangeInfo =====


class TestUIChangeInfo:
    def test_page(self):
        u = UIChangeInfo(path="app/home/page.tsx", type="page")
        assert u.type == "page"
        assert u.is_new is False
        assert u.has_state is False
        assert u.has_effects is False
        assert u.lines_changed == 0

    def test_component(self):
        u = UIChangeInfo(
            path="components/Table.tsx",
            type="component",
            is_new=True,
            has_state=True,
            has_effects=True,
            lines_changed=60,
        )
        assert u.type == "component"
        assert u.has_state is True

    def test_invalid_type(self):
        with pytest.raises(ValidationError) as exc_info:
            UIChangeInfo(path="x.tsx", type="widget")
        assert "type" in str(exc_info.value)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            UIChangeInfo(type="page")  # missing path
        with pytest.raises(ValidationError):
            UIChangeInfo(path="x.tsx")  # missing type


# ===== TestFileInfo =====


class TestTestFileInfo:
    def test_valid(self):
        t = TestFileInfo(path="tests/svc.test.ts", tested_file="lib/svc.ts")
        assert t.path == "tests/svc.test.ts"
        assert t.tested_file == "lib/svc.ts"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            TestFileInfo(tested_file="x")  # missing path
        with pytest.raises(ValidationError):
            TestFileInfo(path="x")  # missing tested_file


# ===== CICheck =====


class TestCICheck:
    def test_success(self):
        c = CICheck(name="lint", status="success")
        assert c.conclusion is None

    def test_failure_with_conclusion(self):
        c = CICheck(name="tests", status="failure", conclusion="Process completed with exit code 1")
        assert c.status == "failure"
        assert c.conclusion == "Process completed with exit code 1"

    def test_pending(self):
        c = CICheck(name="deploy", status="pending")
        assert c.status == "pending"

    def test_invalid_status(self):
        with pytest.raises(ValidationError) as exc_info:
            CICheck(name="x", status="running")
        assert "status" in str(exc_info.value)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            CICheck(status="success")  # missing name
        with pytest.raises(ValidationError):
            CICheck(name="x")  # missing status


# ===== CIStatus =====


class TestCIStatus:
    def test_all_passed_empty(self):
        s = CIStatus(all_passed=True)
        assert s.checks == []

    def test_with_checks(self):
        checks = [
            CICheck(name="lint", status="success"),
            CICheck(name="test", status="failure"),
        ]
        s = CIStatus(all_passed=False, checks=checks)
        assert len(s.checks) == 2
        assert s.all_passed is False

    def test_checks_default_factory(self):
        s1 = CIStatus(all_passed=True)
        s2 = CIStatus(all_passed=True)
        assert s1.checks is not s2.checks

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            CIStatus()  # missing all_passed


# ===== PRAnalysis =====


class TestPRAnalysis:
    def test_defaults(self):
        a = PRAnalysis()
        assert a.classification == "trivial"
        assert a.migrations == []
        assert a.services == []
        assert a.api_routes == []
        assert a.ui_changes == []
        assert a.test_files == []
        assert a.risks == []
        assert a.missing_tests == []
        assert a.total_additions == 0
        assert a.total_deletions == 0

    def test_classification_literals(self):
        for cls in ("major", "minor", "trivial"):
            a = PRAnalysis(classification=cls)
            assert a.classification == cls

    def test_invalid_classification(self):
        with pytest.raises(ValidationError) as exc_info:
            PRAnalysis(classification="huge")
        assert "classification" in str(exc_info.value)

    def test_nested_models(self):
        svc = ServiceChangeInfo(path="a.ts", basename="a")
        route = APIRouteInfo(path="r.ts", endpoint="/r")
        ui = UIChangeInfo(path="u.tsx", type="page")
        tf = TestFileInfo(path="t.test.ts", tested_file="t.ts")
        a = PRAnalysis(
            classification="major",
            services=[svc],
            api_routes=[route],
            ui_changes=[ui],
            test_files=[tf],
            total_additions=500,
            total_deletions=30,
        )
        assert len(a.services) == 1
        assert a.services[0].path == "a.ts"
        assert a.total_additions == 500

    def test_list_default_factories_independent(self):
        a1 = PRAnalysis()
        a2 = PRAnalysis()
        assert a1.migrations is not a2.migrations
        assert a1.services is not a2.services
        assert a1.risks is not a2.risks


# ===== MigrationOperation =====


class TestMigrationOperation:
    @pytest.mark.parametrize(
        "op_type",
        [
            "CREATE_TABLE",
            "ALTER_TABLE",
            "DROP_TABLE",
            "ADD_COLUMN",
            "DROP_COLUMN",
            "ALTER_COLUMN",
            "CREATE_INDEX",
            "ADD_CONSTRAINT",
            "OTHER",
        ],
    )
    def test_all_valid_types(self, op_type):
        op = MigrationOperation(type=op_type, table="users", details="some detail")
        assert op.type == op_type
        assert op.destructive is False

    def test_destructive_flag(self):
        op = MigrationOperation(
            type="DROP_TABLE", table="old_data", details="dropping legacy table", destructive=True
        )
        assert op.destructive is True

    def test_invalid_type(self):
        with pytest.raises(ValidationError) as exc_info:
            MigrationOperation(type="RENAME_TABLE", table="x", details="d")
        assert "type" in str(exc_info.value)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            MigrationOperation(table="x", details="d")  # missing type
        with pytest.raises(ValidationError):
            MigrationOperation(type="OTHER", details="d")  # missing table
        with pytest.raises(ValidationError):
            MigrationOperation(type="OTHER", table="x")  # missing details


# ===== MigrationInfo =====


class TestMigrationInfo:
    def test_minimal(self):
        m = MigrationInfo(path="migrations/001.sql", name="add_users")
        assert m.sql == ""
        assert m.risk_level == "low"
        assert m.operations == []
        assert m.warnings == []
        assert m.rollback_complexity == "easy"

    def test_full(self):
        op = MigrationOperation(type="CREATE_TABLE", table="payments", details="new table")
        m = MigrationInfo(
            path="migrations/002.sql",
            name="add_payments",
            sql="CREATE TABLE payments (...);",
            risk_level="high",
            operations=[op],
            warnings=["Large table creation", "No rollback script"],
            rollback_complexity="hard",
        )
        assert m.risk_level == "high"
        assert len(m.operations) == 1
        assert m.operations[0].table == "payments"
        assert len(m.warnings) == 2
        assert m.rollback_complexity == "hard"

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_valid_risk_levels(self, level):
        m = MigrationInfo(path="m.sql", name="m", risk_level=level)
        assert m.risk_level == level

    def test_invalid_risk_level(self):
        with pytest.raises(ValidationError) as exc_info:
            MigrationInfo(path="m.sql", name="m", risk_level="extreme")
        assert "risk_level" in str(exc_info.value)

    @pytest.mark.parametrize("complexity", ["easy", "medium", "hard", "impossible"])
    def test_valid_rollback_complexity(self, complexity):
        m = MigrationInfo(path="m.sql", name="m", rollback_complexity=complexity)
        assert m.rollback_complexity == complexity

    def test_invalid_rollback_complexity(self):
        with pytest.raises(ValidationError) as exc_info:
            MigrationInfo(path="m.sql", name="m", rollback_complexity="trivial")
        assert "rollback_complexity" in str(exc_info.value)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            MigrationInfo(name="m")  # missing path
        with pytest.raises(ValidationError):
            MigrationInfo(path="m.sql")  # missing name

    def test_list_default_factories(self):
        m1 = MigrationInfo(path="a.sql", name="a")
        m2 = MigrationInfo(path="b.sql", name="b")
        assert m1.operations is not m2.operations
        assert m1.warnings is not m2.warnings


# ===== Risk =====


class TestRisk:
    @pytest.mark.parametrize("level", ["critical", "high", "medium", "low"])
    def test_valid_levels(self, level):
        r = Risk(level=level, category="security", description="something")
        assert r.level == level

    @pytest.mark.parametrize(
        "category",
        ["database", "business-logic", "security", "test-coverage", "performance"],
    )
    def test_valid_categories(self, category):
        r = Risk(level="low", category=category, description="something")
        assert r.category == category

    def test_file_optional(self):
        r = Risk(level="low", category="security", description="d")
        assert r.file is None
        r2 = Risk(level="low", category="security", description="d", file="app.py")
        assert r2.file == "app.py"

    def test_invalid_level(self):
        with pytest.raises(ValidationError):
            Risk(level="extreme", category="security", description="d")

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            Risk(level="low", category="networking", description="d")

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            Risk(category="security", description="d")  # missing level
        with pytest.raises(ValidationError):
            Risk(level="low", description="d")  # missing category
        with pytest.raises(ValidationError):
            Risk(level="low", category="security")  # missing description


# ===== MissingTest =====


class TestMissingTest:
    @pytest.mark.parametrize(
        "reason",
        [
            "new_service_no_test",
            "modified_service_no_test",
            "critical_logic_no_test",
            "api_route_no_test",
        ],
    )
    def test_valid_reasons(self, reason):
        mt = MissingTest(
            service_file="svc.ts",
            reason=reason,
            severity="medium",
            suggested_test_file="svc.test.ts",
        )
        assert mt.reason == reason

    @pytest.mark.parametrize("severity", ["critical", "high", "medium"])
    def test_valid_severities(self, severity):
        mt = MissingTest(
            service_file="svc.ts",
            reason="new_service_no_test",
            severity=severity,
            suggested_test_file="svc.test.ts",
        )
        assert mt.severity == severity

    def test_invalid_reason(self):
        with pytest.raises(ValidationError):
            MissingTest(
                service_file="x",
                reason="unknown_reason",
                severity="medium",
                suggested_test_file="y",
            )

    def test_invalid_severity(self):
        with pytest.raises(ValidationError):
            MissingTest(
                service_file="x",
                reason="new_service_no_test",
                severity="low",
                suggested_test_file="y",
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            MissingTest(
                reason="new_service_no_test",
                severity="medium",
                suggested_test_file="y",
            )


# ===== TestingChecklistItem =====


class TestTestingChecklistItem:
    @pytest.mark.parametrize(
        "category",
        ["pre-flight", "auth", "ui", "data", "calculation", "integration", "edge-case"],
    )
    def test_valid_categories(self, category):
        item = TestingChecklistItem(
            category=category, description="Check something", priority="must"
        )
        assert item.category == category

    @pytest.mark.parametrize("priority", ["must", "should", "nice-to-have"])
    def test_valid_priorities(self, priority):
        item = TestingChecklistItem(
            category="auth", description="Check auth", priority=priority
        )
        assert item.priority == priority

    def test_url_optional(self):
        item = TestingChecklistItem(category="ui", description="d", priority="must")
        assert item.url is None
        item2 = TestingChecklistItem(
            category="ui", description="d", priority="must", url="http://localhost:3000"
        )
        assert item2.url == "http://localhost:3000"

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            TestingChecklistItem(category="unknown", description="d", priority="must")

    def test_invalid_priority(self):
        with pytest.raises(ValidationError):
            TestingChecklistItem(category="ui", description="d", priority="critical")

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            TestingChecklistItem(description="d", priority="must")  # missing category
        with pytest.raises(ValidationError):
            TestingChecklistItem(category="ui", priority="must")  # missing description
        with pytest.raises(ValidationError):
            TestingChecklistItem(category="ui", description="d")  # missing priority


# ===== ReviewRecommendation =====


class TestReviewRecommendation:
    @pytest.mark.parametrize("verdict", ["approve", "request_changes", "needs_discussion"])
    def test_valid_verdicts(self, verdict):
        r = ReviewRecommendation(verdict=verdict)
        assert r.verdict == verdict

    def test_defaults(self):
        r = ReviewRecommendation(verdict="approve")
        assert r.blockers == []
        assert r.required == []
        assert r.suggestions == []

    def test_full(self):
        r = ReviewRecommendation(
            verdict="request_changes",
            blockers=["Missing tests"],
            required=["Add unit tests"],
            suggestions=["Consider integration tests too"],
        )
        assert len(r.blockers) == 1
        assert len(r.required) == 1
        assert len(r.suggestions) == 1

    def test_invalid_verdict(self):
        with pytest.raises(ValidationError):
            ReviewRecommendation(verdict="reject")

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ReviewRecommendation()  # missing verdict

    def test_list_default_factories(self):
        r1 = ReviewRecommendation(verdict="approve")
        r2 = ReviewRecommendation(verdict="approve")
        assert r1.blockers is not r2.blockers
        assert r1.required is not r2.required
        assert r1.suggestions is not r2.suggestions


# ===== NotionSearchResult =====


class TestNotionSearchResult:
    def test_minimal(self):
        n = NotionSearchResult(page_id="abc", title="My Page")
        assert n.page_id == "abc"
        assert n.title == "My Page"
        assert n.url == ""
        assert n.content == ""

    def test_full(self):
        n = NotionSearchResult(
            page_id="xyz",
            title="Design Doc",
            url="https://notion.so/xyz",
            content="Full page content here",
        )
        assert n.url == "https://notion.so/xyz"
        assert n.content == "Full page content here"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            NotionSearchResult(title="X")  # missing page_id
        with pytest.raises(ValidationError):
            NotionSearchResult(page_id="X")  # missing title


# ===== RelevanceScore =====


class TestRelevanceScore:
    def test_minimal(self):
        r = RelevanceScore(page_id="abc", title="Page", score=5.0)
        assert r.score == 5.0
        assert r.url == ""
        assert r.content == ""
        assert r.explanation == ""
        assert r.key_matches == []
        assert r.gaps == []

    def test_full(self):
        r = RelevanceScore(
            page_id="abc",
            title="Design Doc",
            url="https://notion.so/abc",
            content="content",
            score=8.5,
            explanation="Highly relevant",
            key_matches=["payment", "tracking"],
            gaps=["missing export spec"],
        )
        assert r.score == 8.5
        assert len(r.key_matches) == 2
        assert len(r.gaps) == 1

    def test_score_at_boundaries(self):
        r_zero = RelevanceScore(page_id="a", title="t", score=0)
        assert r_zero.score == 0
        r_ten = RelevanceScore(page_id="a", title="t", score=10)
        assert r_ten.score == 10
        r_mid = RelevanceScore(page_id="a", title="t", score=5.5)
        assert r_mid.score == 5.5

    def test_score_below_minimum(self):
        with pytest.raises(ValidationError) as exc_info:
            RelevanceScore(page_id="a", title="t", score=-0.1)
        assert "score" in str(exc_info.value)

    def test_score_above_maximum(self):
        with pytest.raises(ValidationError) as exc_info:
            RelevanceScore(page_id="a", title="t", score=10.1)
        assert "score" in str(exc_info.value)

    def test_score_way_out_of_range(self):
        with pytest.raises(ValidationError):
            RelevanceScore(page_id="a", title="t", score=-100)
        with pytest.raises(ValidationError):
            RelevanceScore(page_id="a", title="t", score=999)

    def test_missing_score(self):
        with pytest.raises(ValidationError):
            RelevanceScore(page_id="a", title="t")  # score has no default

    def test_list_default_factories(self):
        r1 = RelevanceScore(page_id="a", title="t", score=1)
        r2 = RelevanceScore(page_id="b", title="t", score=2)
        assert r1.key_matches is not r2.key_matches
        assert r1.gaps is not r2.gaps


# ===== NotionContext =====


class TestNotionContext:
    def test_minimal(self):
        n = NotionContext(page_id="abc", title="Feature Spec")
        assert n.page_id == "abc"
        assert n.title == "Feature Spec"
        assert n.page_url == ""
        assert n.description == ""
        assert n.requirements == []
        assert n.acceptance_criteria == []
        assert n.raw_content == ""

    def test_full(self):
        n = NotionContext(
            page_id="abc",
            page_url="https://notion.so/abc",
            title="Supplier Payment Tracking",
            description="Track payments per supplier",
            requirements=["Track payments", "Export CSV"],
            acceptance_criteria=["Must handle decimals", "Must support filters"],
            raw_content="Full raw page content",
        )
        assert len(n.requirements) == 2
        assert len(n.acceptance_criteria) == 2
        assert n.raw_content == "Full raw page content"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            NotionContext(title="X")  # missing page_id
        with pytest.raises(ValidationError):
            NotionContext(page_id="X")  # missing title

    def test_list_default_factories(self):
        n1 = NotionContext(page_id="a", title="a")
        n2 = NotionContext(page_id="b", title="b")
        assert n1.requirements is not n2.requirements
        assert n1.acceptance_criteria is not n2.acceptance_criteria


# ===== IntentDelta =====


class TestIntentDelta:
    @pytest.mark.parametrize("status", ["match", "partial", "missing", "extra"])
    def test_valid_statuses(self, status):
        d = IntentDelta(
            aspect="Feature X",
            intended="Do X",
            implemented="Did X",
            status=status,
        )
        assert d.status == status

    def test_all_fields_set(self):
        d = IntentDelta(
            aspect="Payment tracking",
            intended="Track payments per supplier",
            implemented="Payment service with tracking",
            status="match",
        )
        assert d.aspect == "Payment tracking"
        assert d.intended == "Track payments per supplier"
        assert d.implemented == "Payment service with tracking"

    def test_invalid_status(self):
        with pytest.raises(ValidationError) as exc_info:
            IntentDelta(aspect="X", intended="Y", implemented="Z", status="unknown")
        assert "status" in str(exc_info.value)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            IntentDelta(intended="Y", implemented="Z", status="match")  # missing aspect
        with pytest.raises(ValidationError):
            IntentDelta(aspect="X", implemented="Z", status="match")  # missing intended
        with pytest.raises(ValidationError):
            IntentDelta(aspect="X", intended="Y", status="match")  # missing implemented
        with pytest.raises(ValidationError):
            IntentDelta(aspect="X", intended="Y", implemented="Z")  # missing status


# ===== ReviewBrief =====


class TestReviewBrief:
    def test_defaults(self):
        rb = ReviewBrief()
        assert rb.summary == ""
        assert rb.what_was_requested == []
        assert rb.what_was_implemented == []
        assert rb.deltas == []
        assert rb.llm_recommendation == "needs_discussion"
        assert rb.llm_confidence == 0.0
        assert rb.key_concerns == []
        assert rb.positive_findings == []

    def test_full(self):
        delta = IntentDelta(
            aspect="Payment", intended="Track", implemented="Tracked", status="match"
        )
        rb = ReviewBrief(
            summary="Good implementation",
            what_was_requested=["Track payments"],
            what_was_implemented=["Payment service"],
            deltas=[delta],
            llm_recommendation="approve",
            llm_confidence=0.95,
            key_concerns=["No edge case handling"],
            positive_findings=["Clean architecture"],
        )
        assert rb.llm_recommendation == "approve"
        assert rb.llm_confidence == 0.95
        assert len(rb.deltas) == 1

    @pytest.mark.parametrize(
        "recommendation", ["approve", "request_changes", "needs_discussion"]
    )
    def test_valid_recommendations(self, recommendation):
        rb = ReviewBrief(llm_recommendation=recommendation)
        assert rb.llm_recommendation == recommendation

    def test_invalid_recommendation(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewBrief(llm_recommendation="reject")
        assert "llm_recommendation" in str(exc_info.value)

    def test_confidence_at_boundaries(self):
        rb_zero = ReviewBrief(llm_confidence=0.0)
        assert rb_zero.llm_confidence == 0.0
        rb_one = ReviewBrief(llm_confidence=1.0)
        assert rb_one.llm_confidence == 1.0
        rb_mid = ReviewBrief(llm_confidence=0.5)
        assert rb_mid.llm_confidence == 0.5

    def test_confidence_below_minimum(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewBrief(llm_confidence=-0.01)
        assert "llm_confidence" in str(exc_info.value)

    def test_confidence_above_maximum(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewBrief(llm_confidence=1.01)
        assert "llm_confidence" in str(exc_info.value)

    def test_confidence_way_out_of_range(self):
        with pytest.raises(ValidationError):
            ReviewBrief(llm_confidence=-5.0)
        with pytest.raises(ValidationError):
            ReviewBrief(llm_confidence=100.0)

    def test_list_default_factories(self):
        rb1 = ReviewBrief()
        rb2 = ReviewBrief()
        assert rb1.what_was_requested is not rb2.what_was_requested
        assert rb1.what_was_implemented is not rb2.what_was_implemented
        assert rb1.deltas is not rb2.deltas
        assert rb1.key_concerns is not rb2.key_concerns
        assert rb1.positive_findings is not rb2.positive_findings


# ===== Serialization round-trip tests =====


class TestSerialization:
    """Verify models can round-trip through dict / JSON."""

    def test_file_change_round_trip(self):
        fc = FileChange(filename="a.py", status="added", additions=5, patch="+ line")
        data = fc.model_dump()
        fc2 = FileChange(**data)
        assert fc == fc2

    def test_pr_data_round_trip(self):
        pr = PRData(
            number=1,
            title="T",
            author="A",
            files=[FileChange(filename="f.py", status="modified")],
        )
        data = pr.model_dump()
        pr2 = PRData(**data)
        assert pr == pr2

    def test_migration_info_round_trip(self):
        op = MigrationOperation(type="CREATE_TABLE", table="t", details="d", destructive=True)
        m = MigrationInfo(
            path="m.sql",
            name="m",
            operations=[op],
            warnings=["w1"],
            risk_level="high",
            rollback_complexity="impossible",
        )
        data = m.model_dump()
        m2 = MigrationInfo(**data)
        assert m == m2

    def test_review_brief_round_trip(self):
        rb = ReviewBrief(
            summary="s",
            deltas=[
                IntentDelta(aspect="a", intended="i", implemented="impl", status="partial")
            ],
            llm_recommendation="approve",
            llm_confidence=0.9,
        )
        data = rb.model_dump()
        rb2 = ReviewBrief(**data)
        assert rb == rb2

    def test_review_recommendation_round_trip(self):
        r = ReviewRecommendation(
            verdict="request_changes",
            blockers=["b1"],
            required=["r1"],
            suggestions=["s1"],
        )
        json_str = r.model_dump_json()
        r2 = ReviewRecommendation.model_validate_json(json_str)
        assert r == r2

    def test_notion_context_round_trip(self):
        nc = NotionContext(
            page_id="p1",
            title="T",
            requirements=["r1", "r2"],
            acceptance_criteria=["a1"],
        )
        data = nc.model_dump()
        nc2 = NotionContext(**data)
        assert nc == nc2

    def test_relevance_score_json_round_trip(self):
        rs = RelevanceScore(
            page_id="p",
            title="t",
            score=7.5,
            key_matches=["k1"],
            gaps=["g1"],
        )
        json_str = rs.model_dump_json()
        rs2 = RelevanceScore.model_validate_json(json_str)
        assert rs == rs2
