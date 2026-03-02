"""Shared test fixtures."""

from __future__ import annotations

import pytest

from pr_review_agent.models.brief import IntentDelta, ReviewBrief
from pr_review_agent.models.migration import MigrationInfo, MigrationOperation
from pr_review_agent.models.notion import NotionContext, NotionSearchResult, RelevanceScore
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
from pr_review_agent.models.review import (
    MissingTest,
    ReviewRecommendation,
    Risk,
    TestingChecklistItem,
)


@pytest.fixture
def sample_pr_data() -> PRData:
    return PRData(
        number=39,
        title="Add supplier payment tracking",
        author="developer",
        additions=682,
        deletions=35,
        branch="feature/supplier-payments",
        files=[
            FileChange(
                filename="lib/services/payment-service.ts",
                status="added",
                additions=200,
                deletions=0,
                patch="+export function calculatePayment(amount: number, price: number) {\n+  return amount * price;\n+}",
            ),
            FileChange(
                filename="lib/services/csv-export.ts",
                status="added",
                additions=100,
                deletions=0,
                patch="+export function exportToCSV(data: any[]) {\n+  // csv export logic\n+}",
            ),
            FileChange(
                filename="app/api/supplier-payments/route.ts",
                status="added",
                additions=150,
                deletions=0,
                patch="+export async function GET(request: Request) {\n+  // handler\n+}\n+export async function POST(request: Request) {\n+  if (!valid) throw new Error('Invalid');\n+}",
            ),
            FileChange(
                filename="app/payments/page.tsx",
                status="added",
                additions=120,
                deletions=0,
                patch="+import { useState, useEffect } from 'react';\n+export default function PaymentsPage() {}",
            ),
            FileChange(
                filename="components/PaymentTable.tsx",
                status="added",
                additions=80,
                deletions=0,
                patch="+import { useState } from 'react';\n+export function PaymentTable() {}",
            ),
            FileChange(
                filename="prisma/migrations/20240101_add_payments/migration.sql",
                status="added",
                additions=30,
                deletions=0,
                patch='+CREATE TABLE "Payment" (\n+  "id" TEXT NOT NULL,\n+  "amount" DECIMAL NOT NULL\n+);\n+CREATE INDEX "Payment_supplier_idx" ON "Payment"("supplierId");',
            ),
            FileChange(
                filename="tests/lib/services/csv-export.test.ts",
                status="added",
                additions=50,
                deletions=0,
            ),
        ],
    )


@pytest.fixture
def sample_notion_context() -> NotionContext:
    return NotionContext(
        page_id="abc123",
        page_url="https://notion.so/workspace/Payment-Tracking-abc123",
        title="Supplier Payment Tracking",
        description="Track payments per supplier with CSV export capability",
        requirements=[
            "Track payments per supplier",
            "Export payment data to CSV",
            "Payment calculations with decimal precision",
            "API endpoints for CRUD operations",
        ],
        raw_content="Feature: Supplier Payment Tracking\n\nWe need to track payments...",
    )


@pytest.fixture
def sample_analysis(sample_pr_data: PRData) -> PRAnalysis:
    return PRAnalysis(
        classification="major",
        services=[
            ServiceChangeInfo(
                path="lib/services/payment-service.ts",
                basename="payment-service",
                is_new=True,
                has_tests=False,
                lines_changed=200,
                content="calculatePayment amount price",
                contains_financial_logic=True,
            ),
        ],
        api_routes=[
            APIRouteInfo(
                path="app/api/supplier-payments/route.ts",
                endpoint="/supplier-payments",
                methods=["GET", "POST"],
                is_new=True,
                lines_of_logic=150,
                has_business_logic=True,
            ),
        ],
        ui_changes=[
            UIChangeInfo(
                path="app/payments/page.tsx",
                type="page",
                is_new=True,
                has_state=True,
                has_effects=True,
                lines_changed=120,
            ),
        ],
        risks=[
            Risk(
                level="critical",
                category="test-coverage",
                description="payment-service.ts has financial logic but no tests",
                file="lib/services/payment-service.ts",
            ),
        ],
        missing_tests=[
            MissingTest(
                service_file="lib/services/payment-service.ts",
                reason="critical_logic_no_test",
                severity="critical",
                suggested_test_file="tests/lib/services/payment-service.test.ts",
            ),
        ],
        total_additions=682,
        total_deletions=35,
    )


@pytest.fixture
def sample_brief() -> ReviewBrief:
    return ReviewBrief(
        summary="PR adds supplier payment tracking with CSV export.",
        what_was_requested=[
            "Track payments per supplier",
            "Export to CSV",
            "Payment calculations",
        ],
        what_was_implemented=[
            "Payment service with calculation logic",
            "CSV export service",
            "API endpoints for GET/POST",
            "Payment page with table component",
        ],
        deltas=[
            IntentDelta(
                aspect="Payment tracking",
                intended="Track payments per supplier",
                implemented="Payment service created",
                status="match",
            ),
            IntentDelta(
                aspect="CSV export",
                intended="Export payment data to CSV",
                implemented="CSV export service created",
                status="match",
            ),
            IntentDelta(
                aspect="Decimal precision",
                intended="Payment calculations with decimal precision",
                implemented="Basic calculation without explicit precision handling",
                status="partial",
            ),
        ],
        llm_recommendation="request_changes",
        llm_confidence=0.8,
        key_concerns=["No test coverage for financial calculations"],
        positive_findings=["Clean service architecture", "Good API design"],
    )


@pytest.fixture
def sample_recommendation() -> ReviewRecommendation:
    return ReviewRecommendation(
        verdict="request_changes",
        blockers=["1 critical service(s) missing tests: lib/services/payment-service.ts"],
        required=["Add tests for lib/services/payment-service.ts"],
        suggestions=["No test coverage for financial calculations"],
    )
