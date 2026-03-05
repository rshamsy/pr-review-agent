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
