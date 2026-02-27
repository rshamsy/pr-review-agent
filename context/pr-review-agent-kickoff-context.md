# PR / Feature Review Agent — Context Document

> **Purpose:** Import this file into a Claude Code session as foundational context for building the PR/Feature Review Agent. This captures the full product thinking, market research, architecture decisions, and build plan from the initial scoping conversation.

---

## 1. Problem Statement

Vibe coding with AI agents leads to **context explosion** — developers shipping PRs without enough structured review. The goal is a **PR/Feature Review Agent** that:

- Forces context ingestion of the codebase before reviewing
- Pulls intent context from conversations (PM ↔ developer, PM ↔ coding agent)
- Compares **what was intended** vs **what was actually implemented**
- Produces a structured brief for the PM/orchestrator to review
- Conveys a clear change list back to the developer, or triggers a merge

This agent must be in place **before** onboarding the developer onto AI coding tools, so that when PR volume explodes, there's already a review layer handling it.

---

## 2. Full Feature Requirements

### Context Ingestion
- Pull context from PM ↔ developer chat conversations (per feature/PR)
- Pull context from PM notes (Notion, Obsidian, or similar)
- In future: pull context from coding agent sessions (Claude Code, Codex, Cursor)
- Store this as an **intent record** per feature/PR, queryable by branch name or PR title

### Review Planning
- On PR open, classify the change type: UI, backend, database, or mixed
- Generate a **review plan** based on change type — determines which tools to invoke (browser agent, code analysis, DB schema diff, etc.)

### Review Execution
- Run tests (via CI or direct test runner)
- Codebase-aware diff analysis (cross-file impact, not just line-level)
- For UI changes: browser automation (Playwright) to capture screenshots and video of UX flow changes
- Generate Mermaid diagrams for architecture/data flow changes
- Extract relevant code snippets

### PM Brief
- Structured report with:
  - Summary of intended changes (from context)
  - Summary of what was implemented (from codebase + UI)
  - Delta: what matches, what diverges
  - Major vs minor change classification
  - Screenshots/video for UI changes
  - Code diagrams and snippets
  - Confidence score per finding
- Dynamic: option to drill into any section
- Formatted for a non-engineer PM to review

### Feedback Loop
- If changes needed: post review comments to GitHub PR, notify developer
- If approved: trigger merge
- Post-merge: hook into user analytics/logs to verify the feature actually delivered value *(future phase)*

### Future Capabilities
- Agent-to-agent chat: review agent queries coding agent/developer to clarify intent
- PM/orchestrator agent integration
- Multi-PR orchestration (stacked PRs, feature branches)

---

## 3. Market Research Findings

### What Exists Today

| Tool | Strength | Gap vs Our Needs |
|---|---|---|
| **CodeRabbit** | Conversational review inside PR, custom rules, PR summaries | No external context ingestion, no UI review |
| **Greptile** | Full codebase indexing, Mermaid diagrams, cross-file impact | No external context, no UI review, enterprise pricing |
| **Qodo** | Pre-review, test gen, slash commands to auto-fix | No external context, no visual output |
| **Ellipsis** | Reads reviewer comments → auto-commits fixes | No external context, no UI review |
| **Graphite** | Stacked PRs, workflow-level fix | AI is bolt-on, no context layer |
| **Atlassian Rovo Dev** | Pulls acceptance criteria from Jira tickets | Jira-only, text-only, no visual brief |
| **GitHub Copilot PR Review** | Good summaries, low noise | Very light feedback, no context layer |

**Key finding:** No tool ingests your external conversations and notes as intent context. The "intended vs implemented" comparison is entirely unsolved in the market.

### Claude Code (Anthropic)

- Has a `/code-review` command running 4 parallel review agents with confidence scoring
- Has a GitHub Actions integration triggered by `@claude` mentions or PR events
- Has a `/security-review` command with its own GitHub Action
- Context is injected via a static **CLAUDE.md** file (team standards) — not dynamic per-feature intent
- No browser/UI review capability
- No PM brief output

**Best use:** Use Claude Code's GitHub Action as the **execution substrate** — it's the triggered entrypoint. The custom context injection wrapper is what needs to be built on top.

### OpenAI Codex

- Runs tasks in isolated cloud sandboxes with full repo access
- Provides terminal logs and test output citations as evidence
- GPT-5-Codex can take screenshots of its own work (for coding tasks, not external PR review)
- AGENTS.md for per-repo context; Skills for reusable instruction bundles
- Parallel agent execution across multiple PRs/branches

**Key gap:** Screenshots are of Codex's own coding work, not a review of a developer's UI changes. No external context ingestion. No PM brief.

---

## 4. Architecture Plan

### Component Overview

```
┌─────────────────────────────────────────────────────┐
│                   TRIGGER LAYER                      │
│  PR opened on GitHub → GitHub Action fires           │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                  CONTEXT LAYER (RAG)                 │
│  Vector store (Supabase pgvector or Chroma)          │
│  Sources: chat logs, PM notes, agent sessions        │
│  Query: PR title + branch name → intent record       │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                 REVIEW PLANNER (LLM)                 │
│  Input: PR diff + intent record                      │
│  Output: change type classification + tool plan      │
│  Routes to: code analysis / browser agent / both     │
└──────────┬─────────────────────────┬────────────────┘
           │                         │
┌──────────▼──────────┐   ┌──────────▼──────────────┐
│  CODE ANALYSIS      │   │  BROWSER AGENT          │
│  Greptile API       │   │  Playwright + Vision LLM │
│  Cross-file impact  │   │  Screenshots + video     │
│  Mermaid diagrams   │   │  UX flow walkthrough     │
│  Test runner        │   │                          │
└──────────┬──────────┘   └──────────┬───────────────┘
           │                         │
┌──────────▼─────────────────────────▼───────────────┐
│                 BRIEF GENERATOR (LLM)               │
│  Synthesizes all outputs                            │
│  Intended vs Implemented comparison                  │
│  Major/minor classification                          │
│  Structured markdown report for PM                  │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                  FEEDBACK LOOP                       │
│  Changes needed → GitHub PR comments → dev notified  │
│  Approved → trigger merge                            │
│  Post-merge → analytics hook (future)               │
└─────────────────────────────────────────────────────┘
```

### Tech Stack Decisions

- **Orchestration:** LangGraph (handles conditional routing between UI/backend review paths)
- **Code analysis:** Greptile API (tool node)
- **Browser automation:** Playwright + Claude vision (for UI screenshot/video)
- **Vector store:** Supabase pgvector or Chroma
- **Context sources:** Slack/chat export, Notion, Claude conversation history
- **Synthesis model:** Claude (Sonnet or Opus depending on brief complexity)
- **Entrypoint:** Claude Code GitHub Action (customized with dynamic context injection)

---

## 5. Phased Build Plan

### Phase 1 — MVP (Build Now)
**Goal:** Intent vs implementation brief, no tooling dependencies.

- Set up context ingestion pipeline: paste feature conversation summary into a doc per PR
- Agent reads PR diff + feature doc → produces structured brief
- Output: "You asked for X. Here's what was implemented. Here are the deltas."
- Deliverable: markdown brief posted as a GitHub PR comment

**Value:** Immediately more useful than any off-the-shelf tool. Proves the core concept.

### Phase 2 — Codebase Awareness
**Goal:** Add full repo context to the analysis.

- Integrate Greptile API as a tool node in the LangGraph flow
- Brief now includes cross-file impact, architectural diagrams, confidence scores
- Begin building the RAG pipeline for automated context ingestion (vs manual doc paste)

### Phase 3 — UI Review
**Goal:** Add visual review for frontend PRs.

- Browser agent (Playwright) spins up against staging/preview deployment
- Navigates UX flows affected by the PR
- Captures screenshots and video
- Brief includes visual before/after where applicable

**Note:** Most technically complex phase. Requires a staging environment per PR (Vercel preview deployments work well for this).

### Phase 4 — Post-Merge Validation *(Future)*
**Goal:** Close the loop on whether the feature actually delivered value.

- Hook into user analytics (PostHog, Mixpanel, or custom logs)
- Compare expected user behavior change (from intent record) vs actual usage data
- Surface anomalies: "Feature was merged 7 days ago but adoption is 3% vs expected 40%"

---

## 6. Key Design Principles

1. **Context is the differentiator.** Every existing tool starts cold — they only know the diff. This agent knows *why* the PR exists.

2. **The brief is for a PM, not an engineer.** Output must be readable without opening the codebase. Engineers get the inline PR comments; the PM gets the brief.

3. **Dynamic depth.** The brief surface is concise. Every section should be expandable. The PM can drill into code if needed, but shouldn't have to by default.

4. **Small PRs are easier to review well.** Encourage the developer (and coding agents) to keep PRs focused. The review plan should flag oversized PRs.

5. **Don't block shipping.** The agent's job is to surface issues and make the merge decision easier, not to be a gatekeeping bottleneck. If no issues found, merge automatically.

---

## 7. Open Questions / Future Decisions

- [ ] Which vector store to use: Supabase pgvector (already in stack?) vs Chroma
- [ ] Context ingestion UX: manual doc paste (Phase 1) vs automated Slack/Notion connector
- [ ] How to handle PRs with no prior conversation context (cold PRs from the developer)
- [ ] Staging environment strategy for browser agent (Vercel preview? Docker?)
- [ ] Greptile API pricing fit for the volume expected
- [ ] Whether to build the PM brief as a GitHub PR comment, a separate web UI, or a Notion page
- [ ] Agent-to-agent protocol: how does the review agent query the coding agent for clarification?

---

## 8. Reference Tools & Links

- [CodeRabbit](https://www.coderabbit.ai/)
- [Greptile](https://www.greptile.com)
- [Qodo](https://www.qodo.ai/)
- [Ellipsis](https://www.ellipsis.dev/)
- [Graphite](https://graphite.dev/)
- [Claude Code GitHub Action](https://github.com/anthropics/claude-code-action)
- [Claude Code Security Review Action](https://github.com/anthropics/claude-code-security-review)
- [OpenAI Codex](https://openai.com/codex/)
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [Playwright](https://playwright.dev/)
