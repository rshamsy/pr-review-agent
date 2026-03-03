================================================================================
PR REVIEW AGENT - INTEGRATION GUIDE
================================================================================

OVERVIEW
--------
This is an AI-driven PR review agent that compares what was intended (from
Notion docs) against what was actually implemented (from GitHub PRs). It uses
Claude AI to analyze PRs and provide structured review feedback.

Architecture:
  - Python CLI tool (Python 3.11+)
  - LangGraph for workflow orchestration
  - Claude (Anthropic) for AI analysis
  - GitHub CLI for fetching PR data
  - Notion API for fetching context (mandatory)


HOW TO USE THIS IN YOUR NODE PROJECT
================================================================================

STEP 1: PREREQUISITES
---------------------
Install the following on your system:

1. Python 3.11 or higher
   - Check: python3 --version
   - Install: https://www.python.org/downloads/

2. GitHub CLI (gh)
   - Check: gh --version
   - Install: brew install gh (macOS) or see https://cli.github.com/
   - Authenticate: gh auth login

3. pipx (recommended for isolated CLI tools)
   - Check: pipx --version
   - Install: brew install pipx (macOS) or python3 -m pip install --user pipx


STEP 2: INSTALL THE PR REVIEW AGENT
------------------------------------
From your Node project directory, run:

  cd /path/to/pr-review-agent
  pipx install .

Or install from another directory by pointing to the repo path:
  pipx install /path/to/pr-review-agent

To reinstall (e.g. after pulling updates):
  pipx install --force /path/to/pr-review-agent

This installs the 'pr-review' command globally, making it available from any
directory including your Node project.

Alternative (without pipx):
  pip install /path/to/pr-review-agent


STEP 3: CONFIGURE ENVIRONMENT VARIABLES
----------------------------------------
Option A — Use the built-in set-env command (recommended):
  pr-review set-env ANTHROPIC_API_KEY=sk-ant-...
  pr-review set-env NOTION_API_KEY=ntn_...
  pr-review set-env PR_REVIEW_MODEL=claude-sonnet-4-20250514   # optional

This saves values to ~/.config/pr-review-agent/.env so they persist across
sessions and work from any directory.

Option B — Create a .env file in YOUR NODE PROJECT root (or set these globally):

Required:
  ANTHROPIC_API_KEY=sk-ant-...          # Get from https://console.anthropic.com/
  NOTION_API_KEY=ntn_...                # Get from https://www.notion.so/my-integrations

Optional:
  PR_REVIEW_MODEL=claude-sonnet-4-20250514    # Claude model to use

To get your API keys:
  - Anthropic: https://console.anthropic.com/settings/keys
  - Notion: https://www.notion.so/my-integrations
    - Create an integration
    - Grant it access to the pages with your feature docs


STEP 4: RUN THE AGENT FROM YOUR NODE PROJECT
---------------------------------------------
Navigate to your Node project directory where you want to review PRs:

  cd /path/to/your-node-project

Basic usage:
  pr-review 123                # Review PR #123

With options:
  pr-review 123 --verbose      # Show detailed output
  pr-review 123 --post         # Post review comment to GitHub PR
  pr-review 123 --model claude-sonnet-4-20250514

Check configuration:
  pr-review check-config

Set env variables persistently (from any directory):
  pr-review set-env NOTION_API_KEY=ntn_...
  pr-review set-env ANTHROPIC_API_KEY=sk-ant-...


STEP 5: HOW IT WORKS (WORKFLOW)
================================

When you run 'pr-review 123', the agent:

1. FETCH PR DATA
   - Uses 'gh pr view 123' to get PR details, diff, files changed
   - Extracts metadata (title, author, status, CI results)

2. SUMMARIZE PR
   - Uses Claude to generate a summary of what the PR does
   - Identifies key changes (API changes, migrations, UI updates)

3. SEARCH NOTION (MANDATORY)
   - Searches your Notion workspace for relevant docs
   - Uses the PR summary as search context
   - Finds feature specs, design docs, requirements

4. SCORE RELEVANCE
   - Claude scores each Notion result (0-100) for relevance
   - Ranks results to find the most relevant context

5. CONFIRM CONTEXT (INTERACTIVE)
   - Shows you the top Notion results
   - Asks you to confirm if context is sufficient
   - Options:
     * Confirm and proceed
     * Provide specific Notion URL
     * Search again with different terms
     * Exit if no relevant context exists

6. ANALYZE PR
   - Classifies changes (feature, bugfix, refactor, migration)
   - Detects migrations (SQL schema changes, API breaking changes)
   - Analyzes test coverage gaps

7. GENERATE BRIEF (INTENT VS IMPLEMENTATION)
   - Claude compares Notion intent against actual code changes
   - Identifies gaps, deviations, missing requirements
   - Produces structured analysis

8. COMPUTE RECOMMENDATIONS
   - Risk assessment (schema changes, breaking changes)
   - Missing test suggestions
   - Testing checklist

9. FORMAT OUTPUT
   - Displays rich terminal output
   - Optionally posts markdown comment to GitHub PR (--post flag)


ARCHITECTURE DETAILS
================================================================================

Key Components:

/src/pr_review_agent/
  cli.py                    # Entry point (Typer CLI)
  config.py                 # Environment config loader

  graph/
    workflow.py             # LangGraph StateGraph (orchestration)
    nodes.py                # Workflow nodes (each step above)
    state.py                # Shared state (AgentState)
    conditions.py           # Conditional routing

  analyzers/
    pr_analyzer.py          # PR classification, change detection
    migration_analyzer.py   # SQL/API migration analysis
    test_coverage.py        # Test gap detection
    checklist_generator.py  # Testing checklist creation

  notion/
    client.py               # Notion API client (MCP SDK)
    search.py               # Context search
    relevance.py            # Claude-based relevance scoring
    context_loop.py         # Interactive confirmation loop

  github/
    pr_client.py            # GitHub CLI wrapper
    comment.py              # Post comments to PR

  llm/
    brief_generator.py      # Claude: intent vs implementation
    prompts.py              # Prompt templates

  output/
    terminal.py             # Rich console formatting
    markdown.py             # Markdown output


Dependencies (auto-installed):
  - langgraph>=0.2.0              # Workflow orchestration
  - langchain-anthropic>=0.3.0    # Claude integration
  - langchain-core>=0.3.0         # LangChain core
  - mcp>=1.0.0                    # Notion MCP client
  - typer>=0.12.0                 # CLI framework
  - rich>=13.0.0                  # Terminal formatting
  - pydantic>=2.0.0               # Data validation


NOTION INTEGRATION NOTES
================================================================================

Notion context is MANDATORY for this agent. Without it, the agent will block
and prompt you to add context.

Setup:
1. Create a Notion integration at https://www.notion.so/my-integrations
2. Grant it access to pages containing:
   - Feature specifications
   - Design documents
   - Requirements docs
   - Implementation plans
3. Copy the integration token to NOTION_API_KEY

The agent searches Notion based on the PR summary and asks you to confirm
which pages are relevant before proceeding with analysis.


COMMON WORKFLOWS
================================================================================

SCENARIO 1: Review PR in your Node project
  cd /path/to/your-node-project
  pr-review 456

SCENARIO 2: Review and post comment to GitHub
  cd /path/to/your-node-project
  pr-review 456 --post

SCENARIO 3: Review with verbose output for debugging
  cd /path/to/your-node-project
  pr-review 456 --verbose

SCENARIO 4: Add to package.json scripts
  In your Node project's package.json:

  "scripts": {
    "review-pr": "pr-review",
    "review": "pr-review --verbose"
  }

  Then run: npm run review-pr 456


TROUBLESHOOTING
================================================================================

Error: "ANTHROPIC_API_KEY not set"
  Solution: Set environment variable or add to .env file

Error: "NOTION_API_KEY not set"
  Solution: Set environment variable or add to .env file

Error: "gh command not found"
  Solution: Install GitHub CLI (gh) and authenticate with 'gh auth login'

Error: "PR not found"
  Solution: Ensure you're in a git repository with GitHub remote configured

Agent blocks asking for Notion context:
  Solution: This is expected. Provide relevant Notion page URLs when prompted,
  or ensure your Notion workspace has the relevant feature documentation.

Python version error:
  Solution: This requires Python 3.11+. Upgrade Python or use pyenv.


DEVELOPMENT / TESTING
================================================================================

To run tests (optional, for contributors):
  cd /path/to/pr-review-agent
  pip install -e ".[dev]"
  pytest

To reinstall after making changes:
  pipx reinstall pr-review-agent
  # or
  pip install --force-reinstall /path/to/pr-review-agent


ADDITIONAL RESOURCES
================================================================================

GitHub CLI docs: https://cli.github.com/manual/
Notion API: https://developers.notion.com/
Anthropic Claude: https://console.anthropic.com/
LangGraph: https://python.langchain.com/docs/langgraph

Questions? See plans/phase-1-notion-contextual-pr-tests.md for detailed
implementation documentation.
