// Type definitions for PR review script

export interface PRData {
  number: number;
  title: string;
  author: string;
  additions: number;
  deletions: number;
  files: FileChange[];
  branch: string;
}

export interface FileChange {
  filename: string;
  status: 'added' | 'modified' | 'removed';
  additions: number;
  deletions: number;
  patch?: string;
}

export interface PRAnalysis {
  classification: 'major' | 'minor' | 'trivial';
  migrations: MigrationInfo[];
  services: ServiceChangeInfo[];
  apiRoutes: APIRouteInfo[];
  uiChanges: UIChangeInfo[];
  testFiles: TestFileInfo[];
  risks: Risk[];
  missingTests: MissingTest[];
  totalAdditions: number;
  totalDeletions: number;
}

export interface MigrationInfo {
  path: string;
  name: string;
  sql: string;
  riskLevel: 'high' | 'medium' | 'low';
  operations: MigrationOperation[];
  warnings: string[];
  rollbackComplexity: 'easy' | 'medium' | 'hard' | 'impossible';
}

export interface MigrationOperation {
  type: 'CREATE_TABLE' | 'ALTER_TABLE' | 'DROP_TABLE' | 'ADD_COLUMN' |
        'DROP_COLUMN' | 'ALTER_COLUMN' | 'CREATE_INDEX' | 'ADD_CONSTRAINT' | 'OTHER';
  table: string;
  details: string;
  destructive: boolean;
}

export interface ServiceChangeInfo {
  path: string;
  basename: string;
  isNew: boolean;
  hasTests: boolean;
  linesChanged: number;
  content: string;
  containsFinancialLogic: boolean;
}

export interface APIRouteInfo {
  path: string;
  endpoint: string;
  methods: string[];
  isNew: boolean;
  linesOfLogic: number;
  hasBusinessLogic: boolean;
}

export interface UIChangeInfo {
  path: string;
  type: 'page' | 'component';
  isNew: boolean;
  hasState: boolean;
  hasEffects: boolean;
  linesChanged: number;
}

export interface TestFileInfo {
  path: string;
  testedFile: string;
}

export interface Risk {
  level: 'critical' | 'high' | 'medium' | 'low';
  category: 'database' | 'business-logic' | 'security' | 'test-coverage' | 'performance';
  description: string;
  file?: string;
}

export interface MissingTest {
  serviceFile: string;
  reason: 'new_service_no_test' | 'modified_service_no_test' | 'critical_logic_no_test' | 'api_route_no_test';
  severity: 'critical' | 'high' | 'medium';
  suggestedTestFile: string;
}

export interface TestingChecklistItem {
  category: 'pre-flight' | 'auth' | 'ui' | 'data' | 'calculation' | 'integration' | 'edge-case';
  description: string;
  url?: string;
  priority: 'must' | 'should' | 'nice-to-have';
}

export interface CIStatus {
  allPassed: boolean;
  checks: CICheck[];
}

export interface CICheck {
  name: string;
  status: 'success' | 'failure' | 'pending';
  conclusion?: string;
}

export interface ReviewRecommendation {
  verdict: 'approve' | 'request_changes' | 'needs_discussion';
  blockers: string[];
  required: string[];
  suggestions: string[];
}
