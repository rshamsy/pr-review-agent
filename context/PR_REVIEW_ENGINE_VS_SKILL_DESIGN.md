# PR Review: Engine vs Skill — Design & Division of Labor

Status: design reference · Last updated: 2026-06-17

## Why this doc exists

The PR-review process now lives in three places, and it's easy to duplicate
work or put logic in the wrong layer:

1. **`pr-review-agent`** (this repo) — a Python/LangGraph CLI: the deterministic
   engine.
2. **A Claude Code `.md` skill** (e.g. `/pr-review`, to live in the *target*
   repo such as `hubtrack`) — the interactive driver.
3. **Ad-hoc prompting** — asking Claude to review a PR with no codified process.

This doc fixes the seam between them so each piece has one home.

## The core principle

> **Deterministic / batch / unattended work → the engine (this repo).**
> **Judgment / interactive / adaptive work → the skill.**
> **The skill *calls* the engine; it never reimplements it. The engine never
> tries to be interactive.**

Mental model: **`pr-review-agent` is the engine/library; the skill is the
driver/UX.** Pure prompting is the prototype phase — the moment a flow repeats,
it graduates into the skill (if interactive) or the engine (if mechanical).

## The four layers of a review

| # | Layer | Example | Home |
|---|-------|---------|------|
| 1 | **Data gathering** | fetch PR + diff + CI status; recursive Notion intent extraction; 4-tier test-coverage detection; migration risk scoring | **Engine** |
| 2 | **The rubric** | the target repo's review checklist (e.g. HubTrack prod-DB safety, Prisma invariants, RBAC, recon math, intent verification) | **Shared resource file** (lives in the target repo, read by both) |
| 3 | **Orchestration** | independent `agent1` / `agent2` passes → `final` synthesis per PR; cross-PR synthesis | **One home only** — Engine (LangGraph) for batch; Skill (Task subagents) for interactive. Do NOT build in both. |
| 4 | **Judgment + fix loop** | severity verdicts, recommended actions, open questions for the user, then approve → fix → push → comment | **Skill only** (inherently interactive) |

## Responsibility map (current modules → layer)

These modules in `src/pr_review_agent/` are **Layer 1 / engine** and should stay
here — they are deterministic, API-heavy, testable, and runnable headless:

- `github/` (`pr_client.py`, `comment.py`) — PR/diff fetch, CI status, comment posting.
- `notion/` (`client.py`, `context_loop.py`, `relevance.py`, `search.py`) —
  recursive intent-vs-implemented context extraction. **This is the engine's
  crown jewel** and the single hardest thing to reproduce by prompting; keep
  investing here.
- `analyzers/` (`test_coverage.py`, `migration_analyzer.py`, `pr_analyzer.py`,
  `role_detector.py`, `checklist_generator.py`) — deterministic heuristics.
- `models/` — pydantic structures for reproducible, versioned output.
- `output/` (`markdown.py`, `terminal.py`) — structured artifact rendering.
- `llm/` (`brief_generator.py`, `prompts.py`) — one-shot LLM analysis nodes.

`graph/` (LangGraph workflow) is **Layer 3 for the batch/unattended path.** Keep
it for "review all open PRs nightly, post briefs, compare against Notion." Do
**not** also implement the multi-agent passes in the skill if you rely on the
graph here — pick the home that matches how you invoke it.

## The rubric is a shared resource, not code (Layer 2)

The review checklist is **domain knowledge, not logic.** It must NOT be hard-coded
into either the engine or the skill. It lives as a committed markdown file in the
*target* repo and is read by whichever layer is running.

- HubTrack example: `docs/PR_REVIEW_RUBRIC.md` (committed 2026-06; previously an
  untracked working-tree file at risk of deletion). A worked multi-agent example
  is archived at `docs/pr-reviews/2026-05-orchestrator-synthesis.md`.
- The engine reads it as context for its LLM nodes; the skill reads it before
  applying the rubric interactively. One source of truth, two consumers.

## Integration pattern (how the skill uses the engine)

```
/pr-review N
  │
  ├─ 1. read the target repo's PR_REVIEW_RUBRIC.md            (Layer 2)
  ├─ 2. (optional) shell out: `pr-review <N> --json`          (Layer 1 — engine)
  │        → structured brief: Notion intent diff, test-coverage tiers,
  │          migration risk, CI status
  ├─ 3. apply the rubric — single agent, or fan out           (Layer 3, interactive)
  │        agent1 / agent2 independent passes → synthesize
  ├─ 4. present severity-ranked findings to the user          (Layer 4)
  └─ 5. on approval: apply fixes → push → post PR comment     (Layer 4)
```

Step 2 is the seam: the skill does not re-fetch PRs or re-walk Notion — it asks
the engine for the structured brief, then layers judgment and interaction on top.
The engine, run on its own (`pr-review <N>`), is the headless/CI path and skips
steps 3–5 entirely.

## What stays as ad-hoc prompting

Only genuinely novel, one-off situations. The test: if you've prompted the same
review flow twice, it should be codified — interactive flow → skill; mechanical
analysis → engine. (The 2026-06 session that reviewed PRs 94/98/101 by hand was
exactly Layer 4 done manually; it is the canonical thing to capture in `/pr-review`.)

## When to invest where

- **Reach for the engine** when you need: Notion intent-vs-implemented, runs
  across many PRs, scheduled/CI execution, or reproducible structured artifacts.
- **Reach for the skill** when you need: reasoning about business logic,
  interactive verdict + fix/push/comment, or the rubric applied in your normal
  editor/CLI flow.
- **Don't** add interactive fix loops to this engine (Python can't drive them
  well), and **don't** reimplement Notion extraction or coverage heuristics in
  the skill (they belong here, tested).

## Open follow-ups

- [ ] Build the `/pr-review` skill in the target repo(s), per the integration
      pattern above. (Author convention: bundle scripts as files, not inline in
      `SKILL.md`.)
- [ ] Add a `--json` / machine-readable output mode to the CLI if not already
      present, so the skill can consume the engine's brief in step 2.
- [ ] Decide the single home for multi-agent orchestration (graph here vs Task
      subagents in the skill) and remove the other to avoid drift.
