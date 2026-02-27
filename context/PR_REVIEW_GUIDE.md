# PR Review Guide with Claude Code

This guide explains how to review PRs for HubTrack using Claude Code CLI.

## Available Tools

### 1. GitHub Actions (Automatic)
Runs on every PR:
- TypeScript type checking
- ESLint
- Vitest unit tests
- Prisma client generation

### 2. Interactive Review Script
```bash
npm run review -- <PR_NUMBER>
```

### 3. Claude Code CLI (This Guide)
For deeper analysis of business logic, code quality, and migrations.

---

## Review Workflow

### Step 1: Check CI Status
Look at the PR on GitHub for green checkmarks. If CI fails, don't proceed.

### Step 2: Run the Review Script (Optional)
```bash
npm run review -- 40
```
Handles mechanical checks automatically.

### Step 3: Start Claude Code
```bash
claude
```

### Step 4: Get PR Context
Once inside Claude Code, ask:

```
Get the details for PR #40 - title, description, files changed, CI status, and any comments
```

Claude will run `gh pr view`, `gh pr checks`, etc. to gather this info.

### Step 5: Checkout and Analyze
Ask Claude to checkout and review:

```
Checkout PR #40 and review the migration files for safety issues
```

Or be more specific:

```
Checkout PR #40, then:
1. Read the migration SQL files
2. Check for NOT NULL columns without defaults
3. Check for data loss risks
4. Tell me if it's safe to run on a table with existing data
```

### Step 6: Review Business Logic
Ask Claude to analyze specific files:

```
Read lib/services/hub-dashboard.ts and check:
1. Are calculations correct?
2. Any edge cases not handled?
3. Missing null checks?
```

### Step 7: Review Tests
```
Read the test files in this PR and tell me:
1. Do they cover the new functionality?
2. Are there missing edge cases?
3. Is the coverage sufficient?
```

### Step 8: Railway Preview Testing

#### Verify Database Safety (CRITICAL)
1. Go to Railway Dashboard → `hubtrack-pr-XX` environment
2. Check Variables → `DATABASE_URL`
3. Ensure it's NOT production

#### Test the Feature
Open: `https://hubtrack-hubtrack-pr-XX.up.railway.app`

### Step 9: Post Review
Ask Claude:
```
Summarize the issues found and draft a review comment for this PR
```

Or post directly:
```
Post a review comment on PR #40 requesting changes for the migration issue
```

---

## Example Review Session

Here's what an actual review looks like:

**You:** Review PR #40

**Claude:**
- Runs `gh pr view 40` to get details
- Runs `gh pr checks 40` to check CI
- Shows you the summary

**You:** Checkout the PR and review the migration

**Claude:**
- Runs `gh pr checkout 40`
- Reads `prisma/migrations/*/migration.sql`
- Analyzes for risks
- Reports: "This migration adds a NOT NULL column without a default - will fail on non-empty tables"

**You:** What about the tests?

**Claude:**
- Reads test files
- Reports coverage gaps or confirms tests are sufficient

**You:** Post a comment requesting changes

**Claude:**
- Runs `gh pr review 40 --request-changes -b "..."`

---

## Common Review Prompts

### Migration Review
```
Read the migration files in this PR and check:
1. Will it fail on existing data?
2. Is it reversible?
3. Any performance concerns for large tables?
```

### API Route Review
```
Read app/api/trips/[id]/expenses/route.ts and check:
1. Is there proper authentication?
2. Input validation?
3. Error handling?
```

### Service Logic Review
```
Read lib/services/receipt-service.ts and verify:
1. Weight calculations are correct
2. Edge cases handled (null, zero, negative)
3. Transactions used where needed
```

### Test Coverage
```
Compare TESTING_GUIDE.md guidelines to what is actually implemented in the PR
Compare the code changes to the test files. What's missing?
```

### Security Audit
```
Check this PR for:
1. SQL injection risks
2. Missing auth checks
3. Input validation gaps
```

---

## GitHub CLI Commands

Claude can run these for you, but for reference:

```bash
# Get PR details
gh pr view 40

# Check CI status
gh pr checks 40

# Get comments
gh pr view 40 --json comments

# Checkout PR locally
gh pr checkout 40

# Post review comment
gh pr review 40 --comment -b "Your comment here"

# Approve
gh pr review 40 --approve

# Request changes
gh pr review 40 --request-changes -b "Reason"
```

---

## Tips

### Do
- Be specific about what you want reviewed
- Ask Claude to read files before analyzing them
- Verify critical logic yourself (don't blindly trust)
- Test in Railway preview before approving

### Don't
- Approve migrations without reading the SQL
- Skip manual testing for UI changes
- Rush through financial/payment code
- Merge with failing CI

---

## Further Reading

- [PR Review Automation Docs](./PR_REVIEW_AUTOMATION.md)
- [Testing Guide](./TESTING_GUIDE.md)
- [Migration Checklist](../.github/MIGRATION_CHECKLIST.md)
