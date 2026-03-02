import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import type {
  PRData,
  PRAnalysis,
  ServiceChangeInfo,
  APIRouteInfo,
  UIChangeInfo,
  TestFileInfo,
  Risk,
  MissingTest
} from './types.js';

const FINANCIAL_KEYWORDS = ['price', 'payment', 'cost', 'total', 'calculate', 'balance', 'amount'];
const CRITICAL_SERVICES = ['receipt-service', 'bale-production-service', 'hub-dashboard', 'directSupplierService'];

export async function analyzePR(prData: PRData): Promise<PRAnalysis> {
  const services = detectServiceChanges(prData.files);
  const apiRoutes = detectAPIRoutes(prData.files);
  const uiChanges = detectUIChanges(prData.files);
  const testFiles = detectTestFiles(prData.files);
  const missingTests = findMissingTests(services, apiRoutes, testFiles);
  const risks = assessRisks(services, apiRoutes, missingTests);
  const classification = classifyPR(prData, services, risks);

  return {
    classification,
    migrations: [],  // Will be populated by migration-analyzer
    services,
    apiRoutes,
    uiChanges,
    testFiles,
    risks,
    missingTests,
    totalAdditions: prData.additions,
    totalDeletions: prData.deletions
  };
}

function detectServiceChanges(files: any[]): ServiceChangeInfo[] {
  const services: ServiceChangeInfo[] = [];

  for (const file of files) {
    if (!file.filename.includes('lib/services/')) continue;
    if (!file.filename.endsWith('.ts')) continue;

    const basename = file.filename.split('/').pop()!.replace('.ts', '');
    const isNew = file.status === 'added';
    const linesChanged = file.additions + file.deletions;

    // Try to read file content to analyze
    let content = '';
    let containsFinancialLogic = false;
    try {
      const fullPath = join(process.cwd(), file.filename);
      if (existsSync(fullPath)) {
        content = readFileSync(fullPath, 'utf-8');
        containsFinancialLogic = FINANCIAL_KEYWORDS.some(kw =>
          content.toLowerCase().includes(kw)
        );
      }
    } catch (err) {
      // File might not exist locally yet
    }

    // Check if test exists
    const testPath = `tests/lib/services/${basename}.test.ts`;
    const hasTests = files.some(f => f.filename === testPath) ||
                     existsSync(join(process.cwd(), testPath));

    services.push({
      path: file.filename,
      basename,
      isNew,
      hasTests,
      linesChanged,
      content,
      containsFinancialLogic
    });
  }

  return services;
}

function detectAPIRoutes(files: any[]): APIRouteInfo[] {
  const routes: APIRouteInfo[] = [];

  for (const file of files) {
    if (!file.filename.includes('app/api/')) continue;
    if (!file.filename.endsWith('route.ts')) continue;

    const isNew = file.status === 'added';
    const linesOfLogic = file.additions;  // Rough estimate

    // Extract endpoint from path: app/api/supplier-payments/route.ts -> /supplier-payments
    const parts = file.filename.split('/');
    const apiIndex = parts.indexOf('api');
    const endpointParts = parts.slice(apiIndex + 1, -1);  // Remove 'route.ts'
    const endpoint = '/' + endpointParts.join('/');

    // Try to detect methods from content
    let methods: string[] = [];
    let hasBusinessLogic = false;
    try {
      const fullPath = join(process.cwd(), file.filename);
      if (existsSync(fullPath)) {
        const content = readFileSync(fullPath, 'utf-8');
        if (content.includes('export async function GET')) methods.push('GET');
        if (content.includes('export async function POST')) methods.push('POST');
        if (content.includes('export async function PUT')) methods.push('PUT');
        if (content.includes('export async function DELETE')) methods.push('DELETE');
        if (content.includes('export async function PATCH')) methods.push('PATCH');

        // Detect business logic (calculations, validations, etc.)
        hasBusinessLogic = linesOfLogic > 30 ||
                          FINANCIAL_KEYWORDS.some(kw => content.toLowerCase().includes(kw)) ||
                          content.includes('if (') && content.includes('throw');
      }
    } catch (err) {
      // File might not exist locally
    }

    routes.push({
      path: file.filename,
      endpoint,
      methods,
      isNew,
      linesOfLogic,
      hasBusinessLogic
    });
  }

  return routes;
}

function detectUIChanges(files: any[]): UIChangeInfo[] {
  const changes: UIChangeInfo[] = [];

  for (const file of files) {
    const isPage = file.filename.includes('app/') && file.filename.endsWith('page.tsx');
    const isComponent = file.filename.includes('components/') && file.filename.endsWith('.tsx');

    if (!isPage && !isComponent) continue;

    const isNew = file.status === 'added';
    const linesChanged = file.additions + file.deletions;

    let hasState = false;
    let hasEffects = false;
    try {
      const fullPath = join(process.cwd(), file.filename);
      if (existsSync(fullPath)) {
        const content = readFileSync(fullPath, 'utf-8');
        hasState = content.includes('useState') || content.includes('useReducer');
        hasEffects = content.includes('useEffect');
      }
    } catch (err) {
      // File might not exist
    }

    changes.push({
      path: file.filename,
      type: isPage ? 'page' : 'component',
      isNew,
      hasState,
      hasEffects,
      linesChanged
    });
  }

  return changes;
}

function detectTestFiles(files: any[]): TestFileInfo[] {
  const tests: TestFileInfo[] = [];

  for (const file of files) {
    if (!file.filename.includes('tests/')) continue;
    if (!file.filename.endsWith('.test.ts')) continue;

    // Extract tested file: tests/lib/services/foo.test.ts -> lib/services/foo.ts
    const testedFile = file.filename
      .replace('tests/', '')
      .replace('.test.ts', '.ts');

    tests.push({
      path: file.filename,
      testedFile
    });
  }

  return tests;
}

function findMissingTests(
  services: ServiceChangeInfo[],
  apiRoutes: APIRouteInfo[],
  testFiles: TestFileInfo[]
): MissingTest[] {
  const missing: MissingTest[] = [];

  // Check services for missing tests
  for (const service of services) {
    if (service.hasTests) continue;

    let severity: 'critical' | 'high' | 'medium' = 'medium';
    let reason: MissingTest['reason'] = 'modified_service_no_test';

    if (service.isNew) {
      reason = 'new_service_no_test';
      severity = 'high';
    }

    if (service.containsFinancialLogic || CRITICAL_SERVICES.includes(service.basename)) {
      severity = 'critical';
      reason = 'critical_logic_no_test';
    }

    // Only flag if significant changes
    if (service.isNew || service.linesChanged > 50 || service.containsFinancialLogic) {
      missing.push({
        serviceFile: service.path,
        reason,
        severity,
        suggestedTestFile: `tests/lib/services/${service.basename}.test.ts`
      });
    }
  }

  // Check API routes for missing tests
  for (const route of apiRoutes) {
    if (!route.hasBusinessLogic) continue;

    missing.push({
      serviceFile: route.path,
      reason: 'api_route_no_test',
      severity: route.linesOfLogic > 50 ? 'high' : 'medium',
      suggestedTestFile: `tests/${route.path.replace('.ts', '.test.ts')}`
    });
  }

  return missing;
}

function assessRisks(
  services: ServiceChangeInfo[],
  apiRoutes: APIRouteInfo[],
  missingTests: MissingTest[]
): Risk[] {
  const risks: Risk[] = [];

  // Critical: Services with financial logic but no tests
  const criticalMissingTests = missingTests.filter(t => t.severity === 'critical');
  for (const test of criticalMissingTests) {
    risks.push({
      level: 'critical',
      category: 'test-coverage',
      description: `${test.serviceFile} has financial logic but no tests`,
      file: test.serviceFile
    });
  }

  // High: New services without tests
  const newServicesNoTests = services.filter(s => s.isNew && !s.hasTests);
  for (const service of newServicesNoTests) {
    risks.push({
      level: 'high',
      category: 'test-coverage',
      description: `New service ${service.path} has no tests`,
      file: service.path
    });
  }

  // Medium: API routes with business logic
  const complexRoutes = apiRoutes.filter(r => r.hasBusinessLogic);
  for (const route of complexRoutes) {
    risks.push({
      level: 'medium',
      category: 'business-logic',
      description: `API route ${route.endpoint} contains business logic that should be tested`,
      file: route.path
    });
  }

  return risks;
}

function classifyPR(prData: PRData, services: ServiceChangeInfo[], risks: Risk[]): 'major' | 'minor' | 'trivial' {
  const totalLines = prData.additions + prData.deletions;

  // Major if:
  // - Any critical risks
  // - New service without tests
  // - >500 lines changed
  // - Financial logic changes
  if (risks.some(r => r.level === 'critical')) return 'major';
  if (services.some(s => s.isNew && !s.hasTests)) return 'major';
  if (totalLines > 500) return 'major';
  if (services.some(s => s.containsFinancialLogic && s.linesChanged > 50)) return 'major';

  // Minor if:
  // - New files or significant changes
  // - 100-500 lines
  if (totalLines > 100) return 'minor';
  if (services.length > 0 || risks.length > 0) return 'minor';

  return 'trivial';
}
