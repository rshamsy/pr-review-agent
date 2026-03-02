import type { ServiceChangeInfo, APIRouteInfo, MissingTest } from './types.js';

export function analyzeCoverage(
  services: ServiceChangeInfo[],
  apiRoutes: APIRouteInfo[]
): { missingTests: MissingTest[], summary: string } {
  const missing: MissingTest[] = [];

  // Analyze services
  for (const service of services) {
    if (service.hasTests) continue;

    const severity = categorizeSeverity(service);
    const reason = service.isNew ? 'new_service_no_test' :
                   service.containsFinancialLogic ? 'critical_logic_no_test' :
                   'modified_service_no_test';

    // Only flag significant changes
    if (shouldFlagService(service)) {
      missing.push({
        serviceFile: service.path,
        reason,
        severity,
        suggestedTestFile: `tests/lib/services/${service.basename}.test.ts`
      });
    }
  }

  // Analyze API routes
  for (const route of apiRoutes) {
    if (!route.hasBusinessLogic) continue;
    if (route.linesOfLogic < 30) continue;  // Skip trivial routes

    missing.push({
      serviceFile: route.path,
      reason: 'api_route_no_test',
      severity: route.linesOfLogic > 50 ? 'high' : 'medium',
      suggestedTestFile: `tests/${route.path.replace('.ts', '.test.ts')}`
    });
  }

  const summary = generateSummary(missing, services);

  return { missingTests: missing, summary };
}

function categorizeSeverity(service: ServiceChangeInfo): 'critical' | 'high' | 'medium' {
  const criticalServices = [
    'directSupplierService',
    'receipt-service',
    'bale-production-service',
    'hub-dashboard'
  ];

  if (criticalServices.includes(service.basename)) {
    return 'critical';
  }

  if (service.containsFinancialLogic) {
    return 'critical';
  }

  if (service.isNew) {
    return 'high';
  }

  if (service.linesChanged > 50) {
    return 'high';
  }

  return 'medium';
}

function shouldFlagService(service: ServiceChangeInfo): boolean {
  // Always flag new services
  if (service.isNew) return true;

  // Flag if contains financial logic
  if (service.containsFinancialLogic) return true;

  // Flag if significant changes (>50 lines)
  if (service.linesChanged > 50) return true;

  return false;
}

function generateSummary(missing: MissingTest[], services: ServiceChangeInfo[]): string {
  if (missing.length === 0) {
    return '✅ All services and API routes have appropriate test coverage';
  }

  const critical = missing.filter(m => m.severity === 'critical');
  const high = missing.filter(m => m.severity === 'high');
  const medium = missing.filter(m => m.severity === 'medium');

  let summary = `Found ${missing.length} item(s) without tests:\n`;
  if (critical.length > 0) summary += `  🔴 ${critical.length} critical\n`;
  if (high.length > 0) summary += `  🟡 ${high.length} high priority\n`;
  if (medium.length > 0) summary += `  🟢 ${medium.length} medium priority\n`;

  return summary;
}

export function generateTestRecommendations(service: ServiceChangeInfo): string[] {
  const recommendations: string[] = [];

  if (service.containsFinancialLogic) {
    recommendations.push('Test price calculations with decimal precision');
    recommendations.push('Test edge cases: zero, negative, null values');
    recommendations.push('Test calculation accuracy with various inputs');
  }

  if (service.basename.includes('payment') || service.basename.includes('supplier')) {
    recommendations.push('Test payment creation and validation');
    recommendations.push('Test aggregation logic');
    recommendations.push('Test status transitions');
  }

  if (service.basename.includes('csv') || service.content.includes('csv')) {
    recommendations.push('Test CSV export format');
    recommendations.push('Test data accuracy in exported CSV');
  }

  if (service.content.includes('aggregate') || service.content.includes('group')) {
    recommendations.push('Test data grouping logic');
    recommendations.push('Test aggregation with empty results');
  }

  // Generic recommendations
  recommendations.push('Test happy path scenarios');
  recommendations.push('Test error handling');
  recommendations.push('Mock Prisma calls using vi.mock');

  return recommendations;
}
