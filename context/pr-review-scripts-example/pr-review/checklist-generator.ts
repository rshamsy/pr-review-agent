import type {
  PRAnalysis,
  TestingChecklistItem,
  ServiceChangeInfo,
  UIChangeInfo,
  APIRouteInfo,
  MigrationInfo
} from './types.js';

export function generateTestingChecklist(
  prNumber: number,
  analysis: PRAnalysis
): TestingChecklistItem[] {
  const checklist: TestingChecklistItem[] = [];

  // Pre-flight checks (always included)
  checklist.push(...generatePreFlightChecks(prNumber));

  // Migration-specific tests
  if (analysis.migrations.length > 0) {
    checklist.push(...generateMigrationChecks(analysis.migrations));
  }

  // Service-specific tests
  for (const service of analysis.services) {
    checklist.push(...generateServiceTests(service));
  }

  // API route tests
  for (const route of analysis.apiRoutes) {
    checklist.push(...generateAPITests(route));
  }

  // UI tests
  for (const ui of analysis.uiChanges) {
    checklist.push(...generateUITests(ui));
  }

  // Edge case tests
  if (analysis.services.some(s => s.containsFinancialLogic)) {
    checklist.push(...generateEdgeCaseTests(analysis));
  }

  // Sort by priority
  return checklist.sort((a, b) => {
    const priorities = { 'must': 0, 'should': 1, 'nice-to-have': 2 };
    return priorities[a.priority] - priorities[b.priority];
  });
}

function generatePreFlightChecks(prNumber: number): TestingChecklistItem[] {
  return [
    {
      category: 'pre-flight',
      description: 'Go to Railway Dashboard → pr-' + prNumber + ' → Variables',
      priority: 'must'
    },
    {
      category: 'pre-flight',
      description: 'Verify DATABASE_URL points to PR database (NOT production)',
      priority: 'must'
    },
    {
      category: 'pre-flight',
      description: 'If pointing to production, update it and restart deployment',
      priority: 'must'
    },
    {
      category: 'pre-flight',
      description: 'Wait ~2-3 minutes for redeployment to complete',
      priority: 'must'
    },
    {
      category: 'pre-flight',
      description: 'Check deployment logs for "running migrations safely..."',
      priority: 'must'
    },
    {
      category: 'pre-flight',
      description: `Verify database connection at /api/db-check`,
      url: `/api/db-check`,
      priority: 'must'
    }
  ];
}

function generateMigrationChecks(migrations: MigrationInfo[]): TestingChecklistItem[] {
  const checks: TestingChecklistItem[] = [];

  checks.push({
    category: 'data',
    description: `Verify ${migrations.length} migration(s) ran successfully`,
    priority: 'must'
  });

  if (migrations.some(m => m.operations.some(op => op.type === 'CREATE_TABLE'))) {
    checks.push({
      category: 'data',
      description: 'Verify new database tables exist in Prisma Studio',
      priority: 'should'
    });
  }

  if (migrations.some(m => m.operations.some(op => op.type === 'ADD_COLUMN'))) {
    checks.push({
      category: 'data',
      description: 'Verify new columns appear in database',
      priority: 'should'
    });
  }

  return checks;
}

function generateServiceTests(service: ServiceChangeInfo): TestingChecklistItem[] {
  const tests: TestingChecklistItem[] = [];

  // Payment/supplier services
  if (service.basename.includes('payment') || service.basename.includes('supplier')) {
    tests.push({
      category: 'calculation',
      description: `Test ${service.basename} calculations are correct`,
      priority: 'must'
    });

    if (service.content.includes('csv') || service.basename.includes('csv')) {
      tests.push({
        category: 'data',
        description: 'Test CSV export functionality',
        priority: 'should'
      });
    }
  }

  // Receipt service
  if (service.basename.includes('receipt')) {
    tests.push({
      category: 'calculation',
      description: 'Verify weight calculations (net good, net reject)',
      priority: 'must'
    });
  }

  // Bale production
  if (service.basename.includes('bale')) {
    tests.push({
      category: 'data',
      description: 'Test bale production creation and tracking',
      priority: 'must'
    });
  }

  return tests;
}

function generateAPITests(route: APIRouteInfo): TestingChecklistItem[] {
  const tests: TestingChecklistItem[] = [];

  for (const method of route.methods) {
    tests.push({
      category: 'integration',
      description: `Test ${method} ${route.endpoint}`,
      url: route.endpoint,
      priority: route.hasBusinessLogic ? 'must' : 'should'
    });
  }

  return tests;
}

function generateUITests(ui: UIChangeInfo): TestingChecklistItem[] {
  const tests: TestingChecklistItem[] = [];

  if (ui.isNew) {
    tests.push({
      category: 'ui',
      description: `Navigate to ${ui.path.replace('app/', '/').replace('/page.tsx', '')}`,
      url: ui.path.replace('app/', '/').replace('/page.tsx', ''),
      priority: 'must'
    });
  }

  if (ui.hasState) {
    tests.push({
      category: 'ui',
      description: `Test interactive features in ${ui.type} ${ui.path}`,
      priority: 'should'
    });
  }

  return tests;
}

function generateEdgeCaseTests(analysis: PRAnalysis): TestingChecklistItem[] {
  return [
    {
      category: 'edge-case',
      description: 'Test with zero/null values in calculations',
      priority: 'should'
    },
    {
      category: 'edge-case',
      description: 'Test with large dataset (100+ records)',
      priority: 'nice-to-have'
    },
    {
      category: 'edge-case',
      description: 'Test error handling for invalid inputs',
      priority: 'should'
    }
  ];
}

export function formatChecklist(checklist: TestingChecklistItem[]): string {
  let output = '🌐 BROWSER TESTING CHECKLIST\n\n';

  const categories = {
    'pre-flight': { title: 'PRE-FLIGHT (CRITICAL)', items: [] as TestingChecklistItem[] },
    'must': { title: 'MUST TEST', items: [] as TestingChecklistItem[] },
    'should': { title: 'SHOULD TEST', items: [] as TestingChecklistItem[] },
    'nice-to-have': { title: 'NICE TO HAVE', items: [] as TestingChecklistItem[] }
  };

  // Group by category/priority
  for (const item of checklist) {
    if (item.category === 'pre-flight') {
      categories['pre-flight'].items.push(item);
    } else if (item.priority === 'must') {
      categories['must'].items.push(item);
    } else if (item.priority === 'should') {
      categories['should'].items.push(item);
    } else {
      categories['nice-to-have'].items.push(item);
    }
  }

  // Format each category
  for (const [key, group] of Object.entries(categories)) {
    if (group.items.length === 0) continue;

    output += `${group.title}:\n`;
    for (const item of group.items) {
      const url = item.url ? ` (${item.url})` : '';
      output += `  □ ${item.description}${url}\n`;
    }
    output += '\n';
  }

  return output;
}
