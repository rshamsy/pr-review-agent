# Phase 1 (MVP): PR Review Agent — Implementation Plan

## Context

AI-driven development causes "context explosion" — PRs ship without structured review. No existing tool compares **intended vs implemented** using external context. This agent solves that by ingesting feature intent from Notion (mandatory), running code analysis, and using Claude to produce a structured brief comparing what was requested vs what was built.

Phase 1 is a **standalone Python CLI tool** (`pr-review <PR_NUMBER>`) installable via `pip`/`pipx`. It works with any project regardless of tech stack. Built with **LangGraph** for orchestration, **langchain-anthropic** for Claude, and **MCP Python SDK** for Notion integration.

**Notion context is mandatory** — the agent blocks and prompts the user to add context if insufficient. No CLI-based context input. All intent comes from Notion.

---

## Project Structure

```
/workspace/
  pyproject.toml                          # Package config, dependencies, entry point
  .env.example                            # Environment variable template
  .gitignore                              # Updated with Python patterns
  src/
    pr_review_agent/
      __init__.py                         # Package version
      cli.py                              # Typer CLI entry point
      config.py                           # Env config loader (pydantic)
      graph/
        __init__.py
        state.py                          # AgentState TypedDict
        workflow.py                       # LangGraph StateGraph definition
        nodes.py                          # All graph node functions
        conditions.py                     # Conditional edge functions
      models/
        __init__.py
        pr.py                             # PRData, FileChange, PRAnalysis, etc.
        migration.py                      # MigrationInfo, MigrationOperation
        review.py                         # ReviewRecommendation, Risk, MissingTest
        notion.py                         # NotionContext, ContextSufficiency
        brief.py                          # ReviewBrief, IntentDelta
      analyzers/
        __init__.py
        pr_analyzer.py                    # PR classification, service/API/UI detection
        migration_analyzer.py             # SQL parsing, risk assessment
        test_coverage.py                  # Test gap detection
        checklist_generator.py            # Testing checklist
      notion/
        __init__.py
        client.py                         # Notion MCP client (StdioClientTransport)
        search.py                         # Contextual search using PR summary
        relevance.py                      # Claude-based relevance scoring
        context_loop.py                   # Human-in-the-loop confirmation loop
      github/
        __init__.py
        pr_client.py                      # gh CLI wrapper for PR data
        comment.py                        # Post review as PR comment
      llm/
        __init__.py
        brief_generator.py                # Claude call: intent vs implementation
        prompts.py                        # Prompt templates
      output/
        __init__.py
        terminal.py                       # Rich console output
        markdown.py                       # Markdown brief formatter
  tests/
    conftest.py
    test_analyzers/
    test_notion/
    test_graph/
    test_llm/
```

---

## LangGraph State Graph

### State Schema (`graph/state.py`)

```python
class AgentState(TypedDict, total=False):
    pr_number: int
    pr_data: PRData
    ci_status: dict
    diff_text: str
    pr_summary: str                               # Claude-generated summary of what the PR does
    notion_results: list[NotionSearchResult]       # Raw Notion search results
    relevance_scores: list[RelevanceScore]         # Claude-scored relevance per result
    notion_context: NotionContext | None            # User-confirmed context
    user_confirmation: str                         # "confirmed" | "provide_url" | "partial" | "exit"
    user_provided_url: str | None                  # If user provides a specific Notion URL
    pr_analysis: PRAnalysis
    review_brief: ReviewBrief
    recommendation: ReviewRecommendation
    markdown_comment: str
    should_block: bool
    status: str
```

### Graph Flow (`graph/workflow.py`)

```
START
  │
  v
[fetch_pr_data]              ← gh pr view + gh pr diff
  │
  v
[summarize_pr]               ← Quick Claude call to summarize what the PR does
  │
  v
[search_notion]              ← Contextual search using PR summary
  │
  v
[score_relevance]            ← Claude scores each Notion result vs PR
  │
  v
[confirm_context_with_user]  ← Interactive: "Is this the right intent?"
  │
  ├── (confirmed) ──────────────────────────────────→ [analyze_pr]
  ├── (user provides URL) → [fetch_specific_page] ──→ [confirm_context_with_user]  (loop)
  ├── (user says partial) → wait for enrichment ────→ [search_notion]  (loop)
  └── (no match / exit)  → [exit_with_instructions] → END
  │
  v
[analyze_pr]                 ← Ported analyzers (services, migrations, tests, risks)
  │
  v
[generate_llm_brief]        ← Claude: intent vs implementation comparison
  │
  v
[compute_recommendation]     ← Merge LLM + automated blockers
  │
  v
[format_output]              ← Rich terminal + markdown
  │
  v
END
```

The key design: a **human-in-the-loop confirmation loop** after Notion search. The agent presents what it found, the user confirms relevance. If wrong, the user redirects the agent (provide URL, enrich page, or exit). This loop can cycle multiple times until the user is satisfied with the context.

---

## Key Modules

### 1. Notion MCP Client (`notion/client.py`)

- Uses `mcp` Python SDK with `StdioClientTransport`
- Spawns `npx -y @notionhq/notion-mcp-server` as child process
- Auth via `NOTION_API_KEY` env var passed to the MCP server
- Async context manager: `async with client.connect(): ...`
- Methods: `search_pages(query)`, `get_page_content(page_id)`, `get_block_children(block_id)`

### 2. Notion Search (`notion/search.py`) — Contextual Search

Search is **contextual, not keyword-based**. The agent first understands the PR (from title, branch, diff summary), then searches Notion for pages that are semantically relevant to the change.

**Search flow:**
1. Build a contextual query: Use Claude to summarize the PR diff into a 1-2 sentence description of what the PR does
2. Search Notion using that contextual summary (the Notion MCP search supports text queries)
3. For each result, fetch full page content
4. Use Claude to score relevance: "Does this Notion page describe the intent behind this PR?" → score 0-1 with explanation
5. Rank results by relevance score, take top matches

This avoids brittle keyword matching and handles cases where the Notion page title doesn't exactly match the PR title or branch name.

### 3. Context Confirmation Loop (`notion/context_loop.py`) — Human-in-the-Loop

The agent **cannot decide on its own** whether the extracted context is the right intent. Only the user knows. This creates an interactive confirmation loop:

```
┌─────────────────────────────────────────────┐
│ Search Notion for relevant pages            │
│ Score relevance with Claude                 │
└──────────────────┬──────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────┐
│ Present extracted context to user:          │
│   "I found this Notion page: [title]"       │
│   "Summary: [extracted intent]"             │
│   "Relevance score: X/10"                   │
└──────────────────┬──────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────┐
│ Ask: "Is this the intent behind this PR?"   │
│                                             │
│   [1] Yes, proceed with this context        │
│   [2] Partially — but I can add more detail │
│   [3] No — let me provide the right page    │
│   [4] No match exists — I need to create it │
└──────┬───────┬──────────┬──────────┬────────┘
       │       │          │          │
       v       v          v          v
   PROCEED   User adds   User       User exits,
   with      context,    provides   creates Notion
   review    re-search   Notion     page, re-runs
             (loop)      URL →      later
                         fetch →
                         confirm
                         (loop)
```

**Implementation:** Uses `rich.prompt` for interactive terminal prompts.

**Key behaviors:**
- **Option 1 (Yes)**: Context is confirmed. Agent proceeds to analysis + brief generation.
- **Option 2 (Partially)**: User is prompted to go enrich the Notion page. Agent waits, then re-searches and re-presents. Loop continues.
- **Option 3 (Wrong page)**: User pastes a Notion URL. Agent fetches that specific page, presents content, and asks for confirmation again. Loop continues.
- **Option 4 (Nothing exists)**: Agent exits with instructions on what to create in Notion (description, requirements, acceptance criteria) and how to re-run.

**This replaces word-count checks** with a relevance assessment that the user validates. The LLM helps surface the best candidates, but the human makes the final call.

### 3b. Context Relevance Scorer (`notion/relevance.py`)

Uses a lightweight Claude call to assess whether a Notion page is relevant to a PR:

```python
def score_relevance(pr_summary: str, notion_content: str) -> RelevanceScore:
    """Ask Claude: 'Is this Notion page about the same feature as this PR?'
    Returns: score (0-10), explanation, key_matches (what aligns), gaps (what's missing)
    """
```

This is a fast, cheap call (short prompt, short response) separate from the main brief generation call.
Model: `claude-haiku` for cost efficiency — this is just a relevance check, not deep analysis.

### 4. Analyzers (`analyzers/`) — Ported from Existing TypeScript

Source: `/workspace/context/pr-review-scripts-example/pr-review/`

| TypeScript Module | Python Module | Key Changes |
|---|---|---|
| `pr-analyzer.ts` | `pr_analyzer.py` | No disk reads — uses PR diff patches. Configurable path patterns (not just Next.js). |
| `migration-analyzer.ts` | `migration_analyzer.py` | Pure SQL parsing, near 1:1 port. Gets SQL from diff or GitHub API. |
| `test-coverage.ts` | `test_coverage.py` | Minimal changes, functions already pure. |
| `checklist-generator.ts` | `checklist_generator.py` | Railway-specific checks removed. Generic checklist. |
| `cli-prompts.ts` | **Not ported** | Agent is non-interactive. |

**Tech-stack agnostic**: Path patterns for services, routes, UI, tests are configurable defaults covering Next.js, Express, Django, Rails, etc.

### 5. LLM Brief Generator (`llm/brief_generator.py`)

- Uses `langchain-anthropic` `ChatAnthropic`
- Single Claude call per review
- **System prompt**: Role as technical reviewer, structured JSON output rules
- **User prompt**: Notion intent + PR analysis summary + truncated diff (max ~80K chars)
- **Output model** (`ReviewBrief`):
  - `summary`: 2-3 sentence overview
  - `what_was_requested`: list from Notion intent
  - `what_was_implemented`: list from PR diff
  - `deltas`: list of `IntentDelta` (aspect, intended, implemented, status: match/partial/missing/extra)
  - `llm_recommendation`: approve/request_changes/needs_discussion
  - `llm_confidence`: 0.0-1.0
  - `key_concerns`, `positive_findings`

### 6. Recommendation Engine (`graph/nodes.py` → `compute_recommendation`)

**Automated blockers override LLM recommendation:**
- Critical missing tests → `request_changes`
- High-risk migrations → `request_changes`
- Missing intent deltas → `request_changes`

LLM cannot approve if structural issues exist.

### 7. Output (`output/`)

- **Terminal** (`terminal.py`): Rich panels, tables (intent vs implementation deltas), color-coded verdict
- **Markdown** (`markdown.py`): Structured PR comment with sections: Summary, What Was Requested, What Was Implemented, Deltas, Code Analysis, Recommendation
- Posted via `gh pr comment <N> --body-file /tmp/pr-review-comment.md`

---

## CLI Design (`cli.py`)

```bash
# Install globally
pipx install pr-review-agent

# Usage from any project directory
pr-review 42                    # Review PR #42
pr-review 42 --post             # Post comment to GitHub PR
pr-review 42 --verbose          # Detailed output
pr-review 42 --model claude-opus-4-20250514  # Use specific model
pr-review check-config          # Validate env setup

# npm projects can add to package.json:
# "scripts": { "review": "pr-review" }
```

CLI built with `typer`. No interactive prompts — all context from Notion.

---

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "pr-review-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.0",
    "langchain-anthropic>=0.3.0",
    "langchain-core>=0.3.0",
    "mcp>=1.0.0",
    "typer>=0.12.0",
    "rich>=13.0.0",
    "pydantic>=2.0.0",
]

[project.scripts]
pr-review = "pr_review_agent.cli:main"
```

Build backend: `hatchling`. Source layout: `src/pr_review_agent/`.

---

## Configuration (`.env`)

```
# Required
ANTHROPIC_API_KEY=sk-ant-...
NOTION_API_KEY=ntn_...

# Optional
PR_REVIEW_MODEL=claude-sonnet-4-20250514
```

Both API keys are **required**. `pr-review check-config` validates everything including `gh` CLI and `npx` availability.

---

## Key Design Decisions

1. **Python + LangGraph**: Orchestration as a state graph with conditional edges and loops. Extensible for Phase 2 parallel branches (Greptile, browser agent).
2. **Standalone package**: `pip install pr-review-agent` works from any project, any tech stack.
3. **Notion is mandatory, not optional**: Agent blocks if context is insufficient. Enforces "context first" principle.
4. **No CLI context input**: All intent comes from Notion MCP. Ensures single source of truth.
5. **Human-in-the-loop context confirmation**: Agent searches contextually, scores relevance with Claude, but the **user decides** if the context is right. Loops until confirmed or user exits.
6. **Contextual search, not keyword matching**: Uses Claude to summarize the PR, then searches Notion for semantically relevant pages. Claude (haiku) scores relevance.
7. **Analyzers don't read from disk**: Use PR diff patches and GitHub API. Works without local checkout.
8. **Automated blockers override LLM**: Hard rules (missing tests, risky migrations) always win.
9. **3 Claude calls per review**: (1) PR summary for contextual search, (2) relevance scoring (haiku, cheap), (3) main brief generation. Costs still predictable.

---

## Verification

```bash
# Validate setup
pr-review check-config

# Full review (with Notion context)
ANTHROPIC_API_KEY=... NOTION_API_KEY=... pr-review 39

# Post to GitHub
pr-review 39 --post
```

**Checklist:**
- [ ] `pr-review check-config` passes (API keys, gh CLI, npx)
- [ ] `pr-review 39` fetches PR data correctly
- [ ] Notion contextual search finds relevant pages
- [ ] User is prompted to confirm context relevance (interactive loop works)
- [ ] User can provide a specific Notion URL if search results are wrong
- [ ] User can exit if no context exists (with clear instructions on what to add)
- [ ] Code analysis: correct classification, migration detection, test coverage gaps
- [ ] LLM brief: intent vs implementation deltas are accurate
- [ ] Automated blockers override LLM approve when critical tests missing
- [ ] `--post` flag posts well-formatted markdown to PR
- [ ] Works from a non-Python project directory (e.g., npm project)

---

## Step-by-Step Implementation & Testing Plan

### Step 1: Project Scaffold
**Create:** `pyproject.toml`, `.env.example`, `.gitignore`, directory structure with `__init__.py` files

**Test:** Run `pip install -e ".[dev]"` and verify the package installs. Run `pr-review --help` and verify typer shows the help text (will just be a stub at this point).

**Verify:**
```bash
pip install -e ".[dev]"
pr-review --help        # Should print usage info
python -c "import pr_review_agent"  # Should import without error
```

---

### Step 2: Pydantic Models
**Create:** All 5 model files: `models/pr.py`, `models/migration.py`, `models/review.py`, `models/notion.py`, `models/brief.py`

**Test:** Write `tests/test_models.py` — instantiate each model with valid data, verify validation works, test that invalid data raises `ValidationError`.

**Verify:**
```bash
pytest tests/test_models.py -v
```
Expected: All models instantiate correctly. Invalid data (e.g., `severity="invalid"`) raises errors.

---

### Step 3: Configuration
**Create:** `config.py` with `AgentConfig` pydantic model, `get_config()`, `validate_config()`

**Test:** Write `tests/test_config.py` — test with all env vars set, with missing required vars, with defaults.

**Verify:**
```bash
# Should fail validation (no API keys set)
pr-review check-config

# Should pass (with env vars)
ANTHROPIC_API_KEY=test NOTION_API_KEY=test pr-review check-config
```

---

### Step 4: GitHub Client
**Create:** `github/pr_client.py` (fetch_pr, fetch_diff, fetch_ci_checks) and `github/comment.py` (post_pr_comment)

**Test:** Write `tests/test_github/test_pr_client.py`:
- Mock `subprocess.run` to return fixture JSON matching real `gh pr view` output
- Verify `fetch_pr()` returns correct `PRData` model
- Verify `fetch_diff()` returns diff string
- Verify `fetch_ci_checks()` parses check status correctly

**Verify (unit):**
```bash
pytest tests/test_github/ -v
```

**Verify (manual, requires gh auth):**
```bash
python -c "
from pr_review_agent.github.pr_client import fetch_pr, fetch_diff
pr = fetch_pr(39)
print(f'PR #{pr.number}: {pr.title}, {len(pr.files)} files')
diff = fetch_diff(39)
print(f'Diff length: {len(diff)} chars')
"
```
Expected: Real PR data from HubTrack PR #39.

---

### Step 5: Analyzers (Port from TypeScript)
**Create:** All 4 analyzer files by porting from TypeScript originals.

**Reference files:**
- `context/pr-review-scripts-example/pr-review/pr-analyzer.ts` → `analyzers/pr_analyzer.py`
- `context/pr-review-scripts-example/pr-review/migration-analyzer.ts` → `analyzers/migration_analyzer.py`
- `context/pr-review-scripts-example/pr-review/test-coverage.ts` → `analyzers/test_coverage.py`
- `context/pr-review-scripts-example/pr-review/checklist-generator.ts` → `analyzers/checklist_generator.py`
- `context/pr-review-scripts-example/pr-review/types.ts` → already done in Step 2

**Test per analyzer:**

**5a. `migration_analyzer.py`** — Write `tests/test_analyzers/test_migration_analyzer.py`:
- Test `parse_migration_sql()` with fixture SQL: CREATE TABLE, DROP TABLE, ALTER TABLE, ADD COLUMN, etc.
- Verify each returns correct `MigrationOperation` with right type and destructive flag
- Test `assess_migration_risk()`: high for DROP, medium for NOT NULL without DEFAULT, low for safe adds
- Test `assess_rollback_complexity()`: impossible for DROP TABLE, easy for CREATE TABLE

```bash
pytest tests/test_analyzers/test_migration_analyzer.py -v
```

**5b. `pr_analyzer.py`** — Write `tests/test_analyzers/test_pr_analyzer.py`:
- Create fixture `FileChange` lists mimicking real PRs (service files, API routes, UI components, test files)
- Test `detect_service_changes()`: finds `lib/services/*.ts` files, detects financial keywords in patches
- Test `detect_api_routes()`: finds `app/api/*/route.ts`, extracts methods
- Test `classify_pr()`: major (>500 lines + critical risks), minor (>100 lines), trivial (rest)
- Test `find_missing_tests()`: correctly identifies services without matching test files

```bash
pytest tests/test_analyzers/test_pr_analyzer.py -v
```

**5c. `test_coverage.py`** — Write `tests/test_analyzers/test_test_coverage.py`:
- Test severity classification: critical for financial services, high for new services, medium for modified
- Test recommendation generation: correct suggestions per service type

**5d. `checklist_generator.py`** — Write `tests/test_analyzers/test_checklist_generator.py`:
- Test checklist generation for PR with migrations, for PR with only UI changes, for PR with API routes
- Verify correct priority categorization (must/should/nice-to-have)

```bash
pytest tests/test_analyzers/ -v
```
Expected: All 4 analyzer test suites pass.

---

### Step 6: Notion MCP Integration + Context Confirmation Loop
**Create:** `notion/client.py`, `notion/search.py`, `notion/relevance.py`, `notion/context_loop.py`

**6a. MCP Client (`notion/client.py`):**

Write `tests/test_notion/test_client.py`:
- Mock the MCP session to avoid needing a real Notion server
- Verify `search_pages()` calls the correct MCP tool with correct arguments
- Verify `get_page_content()` parses the MCP result correctly

**6b. Contextual Search (`notion/search.py`):**

Write `tests/test_notion/test_search.py`:
- Mock both the Claude summarization call and the Notion MCP search
- Provide a fixture PR with title "Add supplier payment tracking" and a diff summary
- Verify the search query sent to Notion is contextual (based on Claude's summary of the PR), not just keyword extraction
- Verify that multiple Notion results are returned and ranked

**6c. Relevance Scorer (`notion/relevance.py`):**

Write `tests/test_notion/test_relevance.py`:
- Mock Claude (haiku) to return fixture relevance scores
- Test: PR about "payment form" + Notion page about "payment tracking" → high score
- Test: PR about "payment form" + Notion page about "user authentication" → low score
- Verify the scorer returns: score (0-10), explanation, key_matches, gaps

```bash
pytest tests/test_notion/test_relevance.py -v
```

**6d. Context Confirmation Loop (`notion/context_loop.py`):**

Write `tests/test_notion/test_context_loop.py`:
- Mock `rich.prompt` to simulate user responses
- **Test "confirmed" path**: User selects "Yes, proceed" → loop returns confirmed context
- **Test "provide URL" path**: User selects "No, let me provide the right page" → enters URL → agent fetches that page → user confirms → loop returns
- **Test "partial" path**: User selects "Partially" → agent waits → re-searches → user confirms on second round
- **Test "exit" path**: User selects "No match exists" → loop returns with `should_block=True` and exit instructions

```bash
pytest tests/test_notion/test_context_loop.py -v
```

**Verify (manual, requires NOTION_API_KEY + ANTHROPIC_API_KEY):**
```bash
python -c "
import asyncio
from pr_review_agent.notion.client import NotionMCPClient
from pr_review_agent.notion.search import contextual_search
async def test():
    client = NotionMCPClient()
    async with client.connect():
        results = await contextual_search(
            client, pr_summary='Adding supplier payment tracking with CSV export'
        )
        print(f'Found {len(results)} relevant pages')
        for r in results[:3]:
            print(f'  - [{r.relevance_score}/10] {r.title}')
            print(f'    {r.explanation}')
asyncio.run(test())
"
```
Expected: Returns Notion pages ranked by contextual relevance to the PR, not just keyword matches.

```bash
pytest tests/test_notion/ -v
```

---

### Step 7: LLM Brief Generator
**Create:** `llm/prompts.py`, `llm/brief_generator.py`

**Test:** Write `tests/test_llm/test_brief_generator.py`:
- Mock `ChatAnthropic.invoke()` to return a fixture JSON response matching the `ReviewBrief` schema
- Verify the prompt is correctly formatted with all fields populated
- Verify JSON parsing works and returns a valid `ReviewBrief` model
- Test diff truncation: verify long diffs are truncated to max length

```bash
pytest tests/test_llm/ -v
```

**Verify (manual, requires ANTHROPIC_API_KEY):**
```bash
python -c "
from pr_review_agent.llm.brief_generator import generate_brief
from pr_review_agent.models.notion import NotionContext
from pr_review_agent.models.pr import PRData, PRAnalysis
# Create minimal test data
notion = NotionContext(page_id='test', page_url='', title='Payment Form',
    description='Add supplier payment tracking with CSV export',
    requirements=['Track payments per supplier', 'Export to CSV'],
    raw_content='Add supplier payment tracking...')
pr = PRData(number=39, title='Add PRF', author='dev', additions=682,
    deletions=35, files=[], branch='feature/prf')
analysis = PRAnalysis(classification='major')
brief = generate_brief(notion, pr, analysis, 'diff content here...')
print(f'Summary: {brief.summary}')
print(f'Deltas: {len(brief.deltas)}')
print(f'Recommendation: {brief.llm_recommendation}')
"
```
Expected: Claude returns a structured brief with deltas comparing intent vs implementation.

---

### Step 8: LangGraph Workflow
**Create:** `graph/state.py`, `graph/workflow.py`, `graph/nodes.py`, `graph/conditions.py`

**Test:** Write `tests/test_graph/test_workflow.py`:
- **Happy path (user confirms first result)**: Mock all external calls. Mock user prompt to return "confirmed". Verify graph runs all nodes through to `status="complete"`.
- **Loop path (user provides URL)**: Mock user prompt to return "provide_url" on first pass, then "confirmed" on second. Verify graph loops back through `fetch_specific_page` → `confirm_context_with_user` → proceeds.
- **Loop path (user says partial)**: Mock user to return "partial" first, then "confirmed" after re-search. Verify the re-search loop works.
- **Exit path (no match)**: Mock user to return "exit". Verify graph stops with `should_block=True`, exit instructions displayed.
- **No Notion results at all**: Mock Notion search returning empty. Verify graph prompts user with "no results found" and offers to provide URL or exit.

Write `tests/test_graph/test_nodes.py`:
- Test each node function in isolation with fixture state inputs
- Test `summarize_pr` node: given PR data + diff, returns a summary string
- Test `score_relevance` node: given Notion results + PR summary, returns scored results
- Test `confirm_context_with_user` node: given scored results, interacts with user (mocked prompt)

```bash
pytest tests/test_graph/ -v
```

**Verify (integration, all mocked):**
```python
# Run the full graph with all dependencies mocked, user confirms immediately
workflow = build_workflow()
state = workflow.invoke({"pr_number": 39})
assert state["status"] == "complete"
assert state["notion_context"] is not None  # User confirmed
assert state["review_brief"] is not None
```

---

### Step 9: Output Formatting
**Create:** `output/terminal.py`, `output/markdown.py`

**Test:** Write `tests/test_output.py`:
- Create a fixture `ReviewBrief` with known deltas and recommendation
- Verify `format_review_markdown()` produces valid markdown with all sections present
- Verify the markdown contains: header, intent section, implementation section, deltas table, recommendation

```bash
pytest tests/test_output.py -v
```

**Verify (visual):**
```bash
python -c "
from pr_review_agent.output.terminal import display_results
# ... create fixture state dict ...
display_results(fixture_state, verbose=True)
"
```
Expected: Rich-formatted terminal output with panels, tables, and color-coded verdict.

---

### Step 10: CLI Entry Point
**Create:** `cli.py` with `review` and `check-config` commands

**Test:** Write `tests/test_cli.py`:
- Use `typer.testing.CliRunner` to invoke commands
- Mock the workflow to avoid real API calls
- Test `pr-review 39` invokes the workflow with `pr_number=39`
- Test `pr-review 39 --post` sets the post flag
- Test `pr-review check-config` validates config
- Test error cases: missing PR number, invalid PR number

```bash
pytest tests/test_cli.py -v
```

---

### Step 11: Full Integration Test (All Real)
**Prerequisite:** `ANTHROPIC_API_KEY`, `NOTION_API_KEY`, and `gh` CLI authenticated

**Test sequence:**
```bash
# 1. Install the package
pip install -e ".[dev]"

# 2. Validate config
pr-review check-config
# Expected: "All configuration is valid."

# 3. Run against a real PR with insufficient Notion context
pr-review 39
# Expected: BLOCKED — "Insufficient Notion Context" message with suggestions

# 4. Enrich the Notion page (add description + requirements manually)

# 5. Re-run
pr-review 39
# Expected: Full review brief displayed in terminal

# 6. Verify the brief contains:
#    - "What Was Requested" matches Notion page content
#    - "What Was Implemented" matches actual PR changes
#    - Deltas correctly identify matches/gaps
#    - Recommendation accounts for missing tests

# 7. Post to GitHub
pr-review 39 --post
# Expected: Comment appears on the PR

# 8. Run full test suite
pytest --cov=pr_review_agent -v
# Expected: All tests pass, >80% coverage
```

---

### Step 12: Edge Case & Robustness Testing

| Scenario | How to Test | Expected Result |
|---|---|---|
| PR with no matching Notion page | Run against PR with unrelated branch name | User prompted: "No relevant pages found. Provide a URL or exit." |
| Notion page found but irrelevant | Search returns page about different feature | User prompted: "Is this the intent?" → user says No → provide URL or exit |
| User provides wrong URL | User pastes URL to unrelated page | Re-shown context, user says No again → loop continues |
| User confirms on first try | Search finds relevant page, user says Yes | Proceeds immediately to analysis |
| Very large PR diff (>80K chars) | Run against PR with many files | Diff truncated, review still works |
| PR with only migrations | Run against migration-only PR | Focuses on migration risk analysis |
| PR with only UI changes | Run against UI-only PR | No migration warnings, UI checklist generated |
| `gh` CLI not authenticated | Unset GH_TOKEN | Clear error: "GitHub CLI (gh) is not installed or not authenticated" |
| Notion MCP server fails to start | Set invalid NOTION_API_KEY | Clear error: "Failed to connect to Notion" |
| Claude API error | Set invalid ANTHROPIC_API_KEY | Clear error: "Claude API call failed" |
| PR that perfectly matches intent | Rich Notion page + matching implementation | All deltas are "match", verdict: APPROVE |
| PR missing critical feature | Notion says feature X, PR doesn't have it | Delta: "missing", verdict: REQUEST CHANGES |

---

### Summary: Test Pyramid

```
                    /\
                   /  \
                  / E2E \         ← Step 11-12: Real APIs, real PR
                 /________\
                /          \
               / Integration \    ← Step 8: LangGraph with mocked nodes
              /______________\
             /                \
            /   Unit Tests     \  ← Steps 2-7, 9-10: Each module isolated
           /____________________\
```

- **Unit tests** (Steps 2-7, 9-10): Each module tested in isolation with mocks. Fast, deterministic.
- **Integration tests** (Step 8): LangGraph workflow tested with mocked external calls.
- **E2E tests** (Steps 11-12): Full pipeline against real APIs and real PRs. Requires API keys.
