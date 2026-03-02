#!/usr/bin/env tsx

import { execSync } from 'child_process';
import chalk from 'chalk';
import ora from 'ora';
import boxen from 'boxen';
import { analyzePR } from './pr-review/pr-analyzer.js';
import { detectMigrations } from './pr-review/migration-analyzer.js';
import { analyzeCoverage, generateTestRecommendations } from './pr-review/test-coverage.js';
import { generateTestingChecklist, formatChecklist } from './pr-review/checklist-generator.js';
import {
  getPRNumber,
  confirmContinue,
  selectMigrationAction,
  verifyRailwayDatabase,
  askToPostComment
} from './pr-review/cli-prompts.js';
import type { PRData, PRAnalysis, ReviewRecommendation } from './pr-review/types.js';

async function main() {
  console.log(boxen(chalk.bold.blue('HubTrack PR Review Tool'), {
    padding: 1,
    margin: 1,
    borderStyle: 'double'
  }));

  // Step 1: Get PR number
  const prNumber = process.argv[2] ? parseInt(process.argv[2]) : await getPRNumber();

  // Step 2: Verify GitHub CLI
  const spinner = ora('Verifying GitHub CLI...').start();
  try {
    execSync('gh --version', { stdio: 'pipe' });
    spinner.succeed('GitHub CLI is available');
  } catch (err) {
    spinner.fail('GitHub CLI not found');
    console.log(chalk.red('\nPlease install GitHub CLI: https://cli.github.com/'));
    process.exit(1);
  }

  // Step 3: Check Railway DB verification
  console.log(chalk.yellow.bold('\n🔒 RAILWAY DATABASE SAFETY CHECK\n'));
  const verified = await checkRailwayVerification(prNumber);

  if (!verified) {
    console.log(chalk.red('\n⚠️  DATABASE_URL NOT VERIFIED'));
    console.log(chalk.yellow('This PR\'s Railway environment may still point to PRODUCTION database!\n'));
    console.log('Required action:');
    console.log('1. Go to Railway Dashboard → pr-' + prNumber + ' → Variables');
    console.log('2. Update DATABASE_URL to PR-specific database');
    console.log('3. Restart deployment');
    console.log('4. Comment /railway-db-verified on the PR');
    console.log('5. Re-run this review script\n');

    const continueAnyway = await confirmContinue(chalk.red('⚠️  Continue anyway? (NOT RECOMMENDED)'));
    if (!continueAnyway) {
      process.exit(0);
    }
  } else {
    console.log(chalk.green('✅ DATABASE_URL VERIFIED'));
    console.log('Safe to proceed with review.\n');
  }

  // Step 4: Fetch PR data
  spinner.start('Fetching PR data...');
  const prData = await fetchPRData(prNumber);
  spinner.succeed(`Fetched PR #${prNumber}: ${prData.title}`);

  // Step 5: Check CI status
  console.log(chalk.yellow.bold('\n📊 CI/CD STATUS\n'));
  const ciPassed = await checkCIStatus(prNumber);

  if (!ciPassed) {
    console.log(chalk.red('\n⚠️  Some CI checks failed!'));
    const continueAnyway = await confirmContinue('Continue with review despite failures?');
    if (!continueAnyway) {
      process.exit(0);
    }
  }

  // Step 6: Analyze PR
  spinner.start('Analyzing PR changes...');
  let analysis = await analyzePR(prData);

  // Detect migrations
  const migrations = detectMigrations(prData.files);
  analysis.migrations = migrations;
  spinner.succeed('PR analysis complete');

  // Step 7: Display analysis summary
  displayAnalysisSummary(prNumber, prData, analysis);

  // Step 8: Review migrations interactively
  if (migrations.length > 0) {
    await reviewMigrations(migrations);
  }

  // Step 9: Review test coverage
  console.log(chalk.yellow.bold('\n🧪 TEST COVERAGE ANALYSIS\n'));
  const { missingTests, summary } = analyzeCoverage(analysis.services, analysis.apiRoutes);
  console.log(summary);

  if (missingTests.length > 0) {
    displayMissingTests(missingTests, analysis.services);
  }

  // Step 10: Generate browser testing checklist
  console.log(chalk.yellow.bold('\n🌐 BROWSER TESTING CHECKLIST\n'));
  const checklist = generateTestingChecklist(prNumber, analysis);
  console.log(formatChecklist(checklist));

  // Step 11: Railway safety final verification
  console.log(chalk.red.bold('\n🚨 RAILWAY SAFETY VERIFICATION\n'));
  console.log(chalk.yellow(`Before testing in Railway preview:\n`));
  const railwayChecks = await verifyRailwayDatabase();

  if (!railwayChecks.verified || !railwayChecks.restarted || !railwayChecks.migrationsChecked) {
    console.log(chalk.red('\n⚠️  Please complete all Railway safety checks before testing!'));
  }

  // Step 12: Generate recommendation
  const recommendation = generateRecommendation(analysis, missingTests);
  displayRecommendation(recommendation);

  // Step 13: Optional: Post comment
  if (recommendation.verdict === 'request_changes') {
    const shouldPost = await askToPostComment();
    if (shouldPost) {
      await postReviewComment(prNumber, recommendation, analysis, missingTests);
    }
  }

  console.log(chalk.green.bold('\n✅ Review complete!\n'));
}

async function checkRailwayVerification(prNumber: number): Promise<boolean> {
  try {
    const comments = execSync(`gh pr view ${prNumber} --json comments --jq '.comments[].body'`, {
      encoding: 'utf-8'
    });

    return comments.includes('/railway-db-verified');
  } catch (err) {
    return false;
  }
}

async function fetchPRData(prNumber: number): Promise<PRData> {
  const json = execSync(`gh pr view ${prNumber} --json number,title,author,additions,deletions,files,headRefName`, {
    encoding: 'utf-8'
  });

  const data = JSON.parse(json);

  return {
    number: data.number,
    title: data.title,
    author: data.author.login,
    additions: data.additions,
    deletions: data.deletions,
    files: data.files,
    branch: data.headRefName
  };
}

async function checkCIStatus(prNumber: number): Promise<boolean> {
  try {
    const json = execSync(`gh pr view ${prNumber} --json statusCheckRollup`, {
      encoding: 'utf-8'
    });

    const data = JSON.parse(json);
    const checks = data.statusCheckRollup || [];

    let allPassed = true;

    for (const check of checks) {
      const name = check.name || check.context;
      const status = check.conclusion || check.state;

      if (status === 'SUCCESS' || status === 'success') {
        console.log(chalk.green(`✅ ${name}`));
      } else if (status === 'FAILURE' || status === 'failure') {
        console.log(chalk.red(`❌ ${name}`));
        allPassed = false;
      } else {
        console.log(chalk.yellow(`⏳ ${name} (${status})`));
      }
    }

    return allPassed;
  } catch (err) {
    console.log(chalk.yellow('Could not fetch CI status'));
    return true;
  }
}

function displayAnalysisSummary(prNumber: number, prData: PRData, analysis: PRAnalysis) {
  console.log(boxen(
    chalk.bold(`PR #${prNumber} Analysis Summary\n\n`) +
    `Classification: ${getClassificationColor(analysis.classification)}\n` +
    `Additions: ${chalk.green('+' + prData.additions)} | Deletions: ${chalk.red('-' + prData.deletions)}\n\n` +
    `${analysis.migrations.length > 0 ? chalk.red('🔴') : chalk.green('🟢')} Database Migrations: ${analysis.migrations.length}\n` +
    `${analysis.services.length > 0 ? chalk.yellow('🟡') : chalk.green('🟢')} Service Changes: ${analysis.services.length}\n` +
    `${analysis.apiRoutes.length > 0 ? chalk.yellow('🟡') : chalk.green('🟢')} API Routes: ${analysis.apiRoutes.length}\n` +
    `${analysis.uiChanges.length > 0 ? chalk.blue('🔵') : chalk.green('🟢')} UI Changes: ${analysis.uiChanges.length}\n` +
    `${analysis.risks.length > 0 ? chalk.red('⚠️ ') : '✅ '} Risks: ${analysis.risks.length}`,
    { padding: 1, borderStyle: 'round' }
  ));
}

function getClassificationColor(classification: string): string {
  switch (classification) {
    case 'major': return chalk.red.bold('MAJOR CHANGE');
    case 'minor': return chalk.yellow.bold('MINOR CHANGE');
    case 'trivial': return chalk.green.bold('TRIVIAL CHANGE');
    default: return classification;
  }
}

async function reviewMigrations(migrations: any[]) {
  console.log(chalk.yellow.bold('\n📊 DATABASE MIGRATIONS\n'));

  for (let i = 0; i < migrations.length; i++) {
    const migration = migrations[i];
    console.log(chalk.cyan(`\nMigration ${i + 1}/${migrations.length}: ${migration.name}`));
    console.log(chalk.gray('─'.repeat(60)));
    console.log(`Risk Level: ${getRiskColor(migration.riskLevel)}`);
    console.log(`Rollback: ${migration.rollbackComplexity.toUpperCase()}`);
    console.log(`\nOperations:`);

    for (const op of migration.operations) {
      const icon = op.destructive ? chalk.red('⚠️ ') : chalk.green('✅');
      console.log(`  ${icon} ${op.type} on "${op.table}"`);
    }

    if (migration.warnings.length > 0) {
      console.log(`\nWarnings:`);
      for (const warning of migration.warnings) {
        console.log(`  ${warning}`);
      }
    }

    const action = await selectMigrationAction();

    if (action === 'view') {
      console.log(chalk.gray('\n--- SQL ---'));
      console.log(chalk.gray(migration.sql));
      console.log(chalk.gray('--- END SQL ---\n'));
    } else if (action === 'skip') {
      break;
    }
  }
}

function getRiskColor(risk: string): string {
  switch (risk) {
    case 'high': return chalk.red.bold('HIGH');
    case 'medium': return chalk.yellow.bold('MEDIUM');
    case 'low': return chalk.green.bold('LOW');
    default: return risk;
  }
}

function displayMissingTests(missingTests: any[], services: any[]) {
  const critical = missingTests.filter(t => t.severity === 'critical');
  const high = missingTests.filter(t => t.severity === 'high');

  if (critical.length > 0) {
    console.log(chalk.red.bold('\n🔴 CRITICAL:'));
    for (const test of critical) {
      console.log(chalk.red(`   ${test.serviceFile}`));
      console.log(chalk.gray(`   Expected: ${test.suggestedTestFile}`));

      // Find service and show recommendations
      const service = services.find(s => s.path === test.serviceFile);
      if (service) {
        const recommendations = generateTestRecommendations(service);
        console.log(chalk.yellow('   Recommended tests:'));
        recommendations.slice(0, 3).forEach(rec => {
          console.log(chalk.gray(`     - ${rec}`));
        });
      }
      console.log('');
    }
  }

  if (high.length > 0) {
    console.log(chalk.yellow.bold('🟡 HIGH PRIORITY:'));
    for (const test of high) {
      console.log(chalk.yellow(`   ${test.serviceFile}`));
      console.log(chalk.gray(`   Expected: ${test.suggestedTestFile}\n`));
    }
  }
}

function generateRecommendation(analysis: PRAnalysis, missingTests: any[]): ReviewRecommendation {
  const blockers: string[] = [];
  const required: string[] = [];
  const suggestions: string[] = [];

  // Check for critical missing tests
  const criticalTests = missingTests.filter(t => t.severity === 'critical');
  if (criticalTests.length > 0) {
    blockers.push(`${criticalTests.length} critical service(s) without tests`);
    for (const test of criticalTests) {
      required.push(`Add tests for ${test.serviceFile}`);
    }
  }

  // Check for high-risk migrations
  const highRiskMigrations = analysis.migrations.filter(m => m.riskLevel === 'high');
  if (highRiskMigrations.length > 0) {
    blockers.push(`${highRiskMigrations.length} high-risk migration(s)`);
    required.push('Test migrations with realistic data');
  }

  // Suggestions
  const highPriorityTests = missingTests.filter(t => t.severity === 'high');
  if (highPriorityTests.length > 0) {
    suggestions.push(`Consider adding tests for ${highPriorityTests.length} additional service(s)`);
  }

  if (analysis.migrations.length > 0) {
    suggestions.push('Verify database schema changes in Prisma Studio');
  }

  // Determine verdict
  let verdict: ReviewRecommendation['verdict'] = 'approve';
  if (blockers.length > 0) {
    verdict = 'request_changes';
  } else if (analysis.classification === 'major' && suggestions.length > 0) {
    verdict = 'needs_discussion';
  }

  return { verdict, blockers, required, suggestions };
}

function displayRecommendation(recommendation: ReviewRecommendation) {
  console.log(boxen(
    chalk.bold('REVIEW RECOMMENDATION\n\n') +
    `Verdict: ${getVerdictColor(recommendation.verdict)}\n\n` +
    (recommendation.blockers.length > 0 ?
      chalk.red.bold('Blockers:\n') + recommendation.blockers.map(b => `  🔴 ${b}`).join('\n') + '\n\n' : '') +
    (recommendation.required.length > 0 ?
      chalk.yellow.bold('Required Actions:\n') + recommendation.required.map(r => `  📋 ${r}`).join('\n') + '\n\n' : '') +
    (recommendation.suggestions.length > 0 ?
      chalk.cyan('Suggestions:\n') + recommendation.suggestions.map(s => `  💡 ${s}`).join('\n') : ''),
    { padding: 1, borderStyle: 'double' }
  ));
}

function getVerdictColor(verdict: string): string {
  switch (verdict) {
    case 'approve': return chalk.green.bold('✅ APPROVE');
    case 'request_changes': return chalk.red.bold('❌ REQUEST CHANGES');
    case 'needs_discussion': return chalk.yellow.bold('💬 NEEDS DISCUSSION');
    default: return verdict;
  }
}

async function postReviewComment(
  prNumber: number,
  recommendation: ReviewRecommendation,
  analysis: PRAnalysis,
  missingTests: any[]
) {
  const spinner = ora('Posting review comment...').start();

  let comment = `## 🤖 Automated PR Review\n\n`;
  comment += `**Verdict:** ${recommendation.verdict.toUpperCase().replace('_', ' ')}\n\n`;

  if (recommendation.blockers.length > 0) {
    comment += `### 🔴 Blockers\n`;
    for (const blocker of recommendation.blockers) {
      comment += `- ${blocker}\n`;
    }
    comment += '\n';
  }

  if (recommendation.required.length > 0) {
    comment += `### 📋 Required Actions\n`;
    for (const req of recommendation.required) {
      comment += `- ${req}\n`;
    }
    comment += '\n';
  }

  if (missingTests.length > 0) {
    comment += `### Missing Tests\n`;
    const critical = missingTests.filter(t => t.severity === 'critical');
    for (const test of critical) {
      comment += `- **${test.serviceFile}** → \`${test.suggestedTestFile}\`\n`;
    }
    comment += '\n';
  }

  comment += `---\n*Generated by HubTrack PR Review Tool*`;

  try {
    execSync(`gh pr comment ${prNumber} --body "${comment.replace(/"/g, '\\"')}"`, {
      stdio: 'pipe'
    });
    spinner.succeed('Review comment posted');
  } catch (err) {
    spinner.fail('Failed to post comment');
    console.error(err);
  }
}

main().catch((err) => {
  console.error(chalk.red('Error:'), err);
  process.exit(1);
});
