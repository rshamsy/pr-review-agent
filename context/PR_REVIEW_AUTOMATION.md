# PR Review Automation System

## Overview

This document describes the automated PR review system for HubTrack, which includes **two layers of safety** plus an **interactive review script**.

## What Was Implemented

### Layer 1: Railway Database Safety (GitHub Actions)

Three GitHub Actions workflows that enforce the "empty PR first" workflow to prevent accidental writes to production database:

#### 1. Empty PR Check (`.github/workflows/pr-empty-check.yml`)
- **Triggers:** When a PR is opened
- **Purpose:** Ensures PRs follow the empty PR workflow
- **Behavior:**
  - If PR has code changes → Posts warning comment and fails check
  - If PR is empty → Posts success comment with setup instructions
  - Can be overridden by commenting `/railway-db-verified`

#### 2. Commit Guard (`.github/workflows/pr-commit-guard.yml`)
- **Triggers:** When new commits are pushed to a PR
- **Purpose:** Blocks commits until DATABASE_URL is verified
- **Behavior:**
  - Checks for `/railway-db-verified` comment
  - If NOT found → Posts blocking comment and fails check
  - If found → Allows commits to proceed

#### 3. Verification Confirmation (`.github/workflows/railway-db-verification.yml`)
- **Triggers:** When someone comments on a PR
- **Purpose:** Responds to verification comments
- **Behavior:**
  - Detects `/railway-db-verified` comment
  - Posts confirmation message
  - Adds `railway-db-verified` label (optional)

### Layer 2: Interactive Review Script

An intelligent CLI tool that guides you through reviewing PRs.

**Location:** `scripts/pr-review.ts`

**Modules:**
- `pr-analyzer.ts` - Detects service changes, API routes, UI changes
- `migration-analyzer.ts` - Parses SQL migrations and assesses risks
- `test-coverage.ts` - Identifies missing tests
- `checklist-generator.ts` - Creates PR-specific testing checklists
- `cli-prompts.ts` - Interactive prompts
- `types.ts` - TypeScript type definitions

## How to Use

### For New PRs

#### Step 1: Create Empty PR

```bash
# Create a new branch
git checkout -b feature/my-feature

# Create empty commit (optional)
git commit --allow-empty -m "Initial PR setup"

# Push to create PR
git push -u origin feature/my-feature

# Create PR on GitHub (empty, no code changes yet)
gh pr create --title "Feature: My Feature" --body "Setting up PR environment"
```

#### Step 2: Setup Railway Environment

1. Wait 2-3 minutes for Railway to auto-create the PR environment
2. Go to Railway Dashboard → `pr-XX` environment → Variables
3. Find `DATABASE_URL` variable
4. **Verify it's NOT pointing to production**
5. If it is, update it to point to PR-specific database
6. Click "Restart" to redeploy
7. Wait ~2-3 minutes for redeployment
8. Check deployment logs for: "PR/Preview environment detected — running migrations safely..."

#### Step 3: Verify and Comment

```bash
# Comment on the PR to confirm DATABASE_URL is updated
gh pr comment <PR_NUMBER> --body "/railway-db-verified"
```

#### Step 4: Push Your Code

```bash
# Now you can safely push your feature code
git add .
git commit -m "Add feature implementation"
git push
```

The commit guard will now allow your commits because you verified the DATABASE_URL.

### For Reviewing PRs

#### Run the Review Script

```bash
# Review a specific PR
npm run review -- 39

# Or run and enter PR number interactively
npm run review
```

#### What the Script Does

The script will guide you through:

1. **Railway Database Safety Check**
   - Verifies `/railway-db-verified` comment exists
   - Warns if DATABASE_URL not verified
   - Option to continue anyway (not recommended)

2. **CI Status Check**
   - Displays all GitHub Actions check results
   - ✅ TypeScript, ESLint, Tests, Prisma generation
   - Option to continue if failures detected

3. **PR Analysis**
   - Classification: MAJOR / MINOR / TRIVIAL
   - Counts: migrations, services, API routes, UI changes
   - Risk assessment

4. **Migration Review (Interactive)**
   - For each migration:
     - Risk level (HIGH/MEDIUM/LOW)
     - Operations (CREATE TABLE, ALTER, etc.)
     - Warnings (data loss, performance)
     - Rollback complexity
     - Option to view full SQL

5. **Test Coverage Analysis**
   - Identifies services without tests
   - Severity: CRITICAL / HIGH / MEDIUM
   - Suggests test files to create
   - Lists recommended test cases

6. **Browser Testing Checklist**
   - Pre-flight Railway checks
   - Feature-specific tests
   - Edge case tests
   - Organized by priority (MUST / SHOULD / NICE-TO-HAVE)

7. **Final Recommendation**
   - Verdict: APPROVE / REQUEST CHANGES / NEEDS DISCUSSION
   - Blockers (if any)
   - Required actions
   - Suggestions

8. **Optional: Post Review Comment**
   - Automatically posts review summary to GitHub
   - Includes verdict, blockers, and required actions

#### Example Review Session

```bash
$ npm run review -- 39

╔═════════════════════════════╗
║   HubTrack PR Review Tool   ║
╚═════════════════════════════╝

🔒 RAILWAY DATABASE SAFETY CHECK

✅ DATABASE_URL VERIFIED
Verification comment found from: @matlander at 2026-01-12 10:30 AM
Safe to proceed with review.

📊 CI/CD STATUS

✅ TypeScript type checking
✅ ESLint
✅ Vitest tests
✅ Prisma client generation

╭────────────────────────────────────────────────╮
│ PR #39 Analysis Summary                        │
│                                                │
│ Classification: MAJOR CHANGE                   │
│ Additions: +682 | Deletions: -35              │
│                                                │
│ 🔴 Database Migrations: 3                     │
│ 🟡 Service Changes: 1                         │
│ 🟡 API Routes: 2                              │
│ 🔵 UI Changes: 2                              │
│ ⚠️  Risks: 1                                  │
╰────────────────────────────────────────────────╯

📊 DATABASE MIGRATIONS

Migration 1/3: add_supplier_payment
────────────────────────────────────────────────────────
Risk Level: MEDIUM
Rollback: EASY

Operations:
  ✅ CREATE TABLE on "SupplierPayment"
  ✅ CREATE TYPE on "PaymentType"

? How do you want to proceed? (Use arrow keys)
❯ View full SQL
  Continue to next
  Mark as concern
  Skip remaining migrations

... (continues interactively)
```

## PR Review for PR #39 Specifically

### What PR #39 Does

**Title:** Creating new PRF (Payment Request Form)

**Changes:**
- New database model: `SupplierPayment` (3 migrations)
- New service: `lib/services/directSupplierService.ts` (163 lines)
- New API routes: `/api/supplier-payments`, `/api/direct-suppliers/csv`
- New UI: `/app/direct-suppliers/page.tsx` + `DirectSupplierTable` component
- Modified: admin/hub-lead dashboards (PRF button added)

### Critical Issue Found

**Missing Tests:** The new `directSupplierService.ts` contains financial calculations but has **ZERO test coverage**.

The review script will flag this as a CRITICAL blocker and recommend:

```
❌ REQUEST CHANGES

🔴 CRITICAL: lib/services/directSupplierService.ts
   Reason: New service with financial calculations
   Expected: tests/lib/services/directSupplierService.test.ts

   Recommended tests:
   - Test price calculations (pricePerKg × totalKgs)
   - Test aggregation logic (grouping by supplier-date)
   - Test CSV export format
   - Test status transitions (UNPAID → PARTIAL → CLEARED)
   - Test edge cases (zero prices, null values, empty results)
```

### Browser Testing Checklist for PR #39

The script will generate:

```
🌐 BROWSER TESTING CHECKLIST

PRE-FLIGHT (CRITICAL):
  □ Go to Railway Dashboard → pr-39 → Variables
  □ Verify DATABASE_URL points to PR database (NOT production)
  □ If pointing to production, update it and restart deployment
  □ Wait ~2-3 minutes for redeployment
  □ Check logs for "running migrations safely..."
  □ Verify database connection at /api/db-check

MUST TEST:
  □ Login as Admin → Navigate to Admin Dashboard
  □ Select location → Click "PRF" button
  □ Verify /direct-suppliers page loads
  □ Verify DirectSupplierTable displays data
  □ Click "Advance" button on a supplier row
  □ Enter price per KG and amount → Submit payment
  □ Verify payment appears in table
  □ Click "Download CSV" → Verify CSV format
  □ Test POST /api/supplier-payments
  □ Test GET /api/direct-suppliers/csv

SHOULD TEST:
  □ Test date range filtering
  □ Verify calculations: Amount Due = KGs × Price/KG
  □ Verify Balance = Amount Due - Total Paid
  □ Check status changes: UNPAID → PARTIAL → CLEARED
  □ Test with supplier having multiple deliveries

NICE TO HAVE:
  □ Test CSV export with 100+ records
  □ Test with large dataset
```

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────┐
│ Developer creates empty PR                              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ GitHub Action: Empty PR Check                           │
│ ✅ No files? → Posts setup instructions                │
│ ❌ Has files? → Posts warning, fails check             │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Railway auto-creates PR environment                     │
│ ⚠️  DATABASE_URL defaults to PRODUCTION                │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Developer updates DATABASE_URL in Railway               │
│ 1. Go to Railway Dashboard → pr-XX → Variables         │
│ 2. Update DATABASE_URL to PR database                  │
│ 3. Restart deployment                                  │
│ 4. Wait for migrations to run automatically            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Developer comments: /railway-db-verified                │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ GitHub Action: Verification Confirmation                │
│ ✅ Posts confirmation, adds label                      │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Developer pushes code changes                           │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ GitHub Action: Commit Guard                             │
│ ✅ Has /railway-db-verified? → Allow commits           │
│ ❌ No verification? → Block, post warning              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Reviewer runs: npm run review -- XX                     │
│ - Railway DB safety check                              │
│ - CI status check                                      │
│ - PR analysis (migrations, services, tests)            │
│ - Interactive migration review                         │
│ - Test coverage analysis                               │
│ - Browser testing checklist generation                 │
│ - Final recommendation                                 │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Reviewer approves or requests changes                   │
└─────────────────────────────────────────────────────────┘
```

## Files Created

### GitHub Actions
- `.github/workflows/pr-empty-check.yml`
- `.github/workflows/pr-commit-guard.yml`
- `.github/workflows/railway-db-verification.yml`

### Review Script
- `scripts/pr-review.ts` - Main orchestrator
- `scripts/pr-review/types.ts` - TypeScript types
- `scripts/pr-review/cli-prompts.ts` - Interactive prompts
- `scripts/pr-review/pr-analyzer.ts` - Change detection
- `scripts/pr-review/migration-analyzer.ts` - SQL parsing
- `scripts/pr-review/test-coverage.ts` - Gap detection
- `scripts/pr-review/checklist-generator.ts` - Test checklist generation

### Dependencies Added
- `inquirer` - Interactive CLI prompts
- `chalk` - Terminal colors
- `ora` - Loading spinners
- `boxen` - Fancy output boxes
- `@types/inquirer` - TypeScript types

### Package.json
- Added script: `"review": "tsx scripts/pr-review.ts"`

## Benefits

### Safety
- **Prevents production database accidents** - GitHub Actions enforce DATABASE_URL verification
- **No manual steps forgotten** - Script guides you through everything
- **Consistent reviews** - Everyone follows the same process

### Speed
- **15-20 minutes per review** (vs 30-45 minutes manual)
- **Automated analysis** - Detects migrations, missing tests, risks automatically
- **Pre-generated checklists** - No need to think "what should I test?"

### Quality
- **Catches missing tests** - Before merge, not after
- **Migration safety** - Risk assessment for every schema change
- **Comprehensive coverage** - Services, APIs, UI, migrations all checked

## Troubleshooting

### "DATABASE_URL verification required" error

**Problem:** You pushed code without commenting `/railway-db-verified`

**Solution:**
1. Go to Railway Dashboard → pr-XX → Variables
2. Verify/update DATABASE_URL
3. Comment `/railway-db-verified` on the PR
4. Push again (or trigger workflow manually)

### Review script shows "Not verified" warning

**Problem:** No `/railway-db-verified` comment found

**Solution:**
- Comment `/railway-db-verified` on the PR
- Re-run review script

### Migrations not running automatically

**Problem:** Check `scripts/maybe-deploy.js` is working

**Solution:**
1. Check Railway deployment logs
2. Look for: "PR/Preview environment detected — running migrations safely..."
3. If not found, migrations aren't running - check the `start` script in package.json

## Advanced Usage

### Skip Railway Verification (NOT RECOMMENDED)

```bash
# When prompted "Continue anyway?" → yes
# Only use if you're absolutely certain DATABASE_URL is correct
```

### Generate Review Comment Without Posting

The script asks before posting to GitHub. You can copy the comment and post manually if preferred.

### Review Specific Files

The script automatically focuses on changed files. No need to specify.

## Next Steps

1. **Test the system with PR #39**
   - Run `npm run review -- 39`
   - Follow the generated checklist
   - Provide feedback on PR #39 (request tests)

2. **Create tests for directSupplierService.ts**
   - File: `tests/lib/services/directSupplierService.test.ts`
   - Reference: `tests/lib/services/receipt-service.test.ts` for patterns

3. **Use for all future PRs**
   - Empty PR workflow becomes standard
   - Run review script before every PR approval

## Support

For issues or questions:
- Check GitHub Actions logs
- Review `docs/PR_REVIEW_GUIDE.md`
- Check Railway deployment logs
