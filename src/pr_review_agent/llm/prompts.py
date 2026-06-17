"""Prompt templates for Claude LLM calls."""

SUMMARIZE_PR_SYSTEM = """You are a technical assistant. Given PR metadata and a diff, write a 1-2 sentence summary of what this PR does. Focus on the feature/change, not implementation details.

Respond with ONLY the summary text, no other formatting."""

SUMMARIZE_PR_USER = """PR #{pr_number}: {pr_title}
Branch: {branch}
Author: {author}
Files changed: {file_count}
+{additions} / -{deletions}

Diff (truncated):
{diff_preview}"""


REVIEW_BRIEF_SYSTEM = """You are a senior technical reviewer. You are given:
1. The **intended feature** (from one or more Notion spec/requirements pages)
2. The **CI/CD status** (automated test and build results)
3. The **PR analysis** (automated analysis of what changed, including detailed migration info)
4. The **PR diff** (actual code changes)

Your job: Compare what was requested vs what was implemented. Produce a structured review brief.

Consider CI failures as potential blockers. Analyze migration details for data safety risks.
If tests are failing, mention them in key_concerns.

Respond with a JSON object matching this exact schema:
{{
  "summary": "<2-3 sentence overview of the PR>",
  "what_was_requested": ["<item from Notion requirements>", ...],
  "what_was_implemented": ["<item from PR diff>", ...],
  "deltas": [
    {{
      "aspect": "<feature aspect>",
      "intended": "<what the spec says>",
      "implemented": "<what the PR does>",
      "status": "match" | "partial" | "missing" | "extra"
    }}
  ],
  "llm_recommendation": "approve" | "request_changes" | "needs_discussion",
  "llm_confidence": <0.0-1.0>,
  "key_concerns": ["<concern>", ...],
  "positive_findings": ["<positive>", ...]
}}

Delta status meanings:
- "match": Implementation fully matches the requirement
- "partial": Partially implemented or implemented differently
- "missing": Requirement exists in spec but not in PR
- "extra": Implementation exists in PR but not in spec

Be thorough but fair. Flag real issues, acknowledge good work.
Respond ONLY with the JSON object."""


REVIEW_BRIEF_USER = """## Notion Intent (Feature Spec)
{notion_section}

## CI/CD Status
{ci_status_summary}

## PR Analysis
Classification: {classification}
Services changed: {services_summary}
API routes: {api_routes_summary}
UI changes: {ui_changes_summary}

Migrations:
{migrations_summary}

Missing tests: {missing_tests_summary}
Risks: {risks_summary}

## PR Diff
{diff_text}"""


ROLE_TESTING_SYSTEM = """You are a QA testing specialist focused on role-based access control (RBAC) testing.

Given code snippets containing role/auth patterns, Notion feature context, and changed routes/pages,
produce role-specific testing pathways that a reviewer can follow to verify access control behavior.

Each pathway targets a specific user role and lists:
- Which routes/pages are accessible to that role
- Which routes/pages should be restricted
- Step-by-step testing actions with expected outcomes

Respond with a JSON object matching this exact schema:
{{
  "pathways": [
    {{
      "role": "<role name, e.g. admin, supplier, buyer>",
      "description": "<1-sentence description of what this role should be able to do>",
      "login_hint": "<how to log in as this role, e.g. test credentials or method>",
      "accessible_routes": ["<route or page this role CAN access>"],
      "restricted_routes": ["<route or page this role should NOT access>"],
      "steps": [
        {{
          "action": "<what to do, e.g. Navigate to /admin/users>",
          "expected": "<what should happen, e.g. Page loads with user list>",
          "url": "<optional URL or route>",
          "priority": "must" | "should" | "nice-to-have"
        }}
      ]
    }}
  ]
}}

Guidelines:
- Only include roles that are relevant to the changed code
- Focus steps on verifying the specific changes in this PR
- Include both positive tests (role CAN do X) and negative tests (role CANNOT do Y)
- Keep steps actionable and specific
- Prioritize security-critical checks as "must"

Respond ONLY with the JSON object."""


ROLE_TESTING_USER = """## Detected Roles
{detected_roles}

## Auth Patterns Found
{auth_patterns}

## Role-Related Code Snippets
{role_snippets}

## Feature Context (from Notion)
{notion_summary}

## Changed API Routes
{api_routes}

## Changed UI Pages
{ui_pages}"""
