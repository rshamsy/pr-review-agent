import { readFileSync, existsSync, readdirSync } from 'fs';
import { join } from 'path';
import type { MigrationInfo, MigrationOperation } from './types.js';

export function detectMigrations(files: any[]): MigrationInfo[] {
  const migrations: MigrationInfo[] = [];

  for (const file of files) {
    if (!file.filename.includes('prisma/migrations/')) continue;
    if (!file.filename.endsWith('migration.sql')) continue;

    try {
      const fullPath = join(process.cwd(), file.filename);
      if (existsSync(fullPath)) {
        const migration = analyzeMigration(file.filename, fullPath);
        migrations.push(migration);
      }
    } catch (err) {
      console.error(`Error analyzing migration ${file.filename}:`, err);
    }
  }

  // Also check for any new migration directories
  const migrationsDir = join(process.cwd(), 'prisma/migrations');
  if (existsSync(migrationsDir)) {
    const dirs = readdirSync(migrationsDir, { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => d.name);

    for (const dir of dirs) {
      const sqlFile = join(migrationsDir, dir, 'migration.sql');
      if (existsSync(sqlFile)) {
        const relativePath = `prisma/migrations/${dir}/migration.sql`;
        // Only add if not already in migrations array
        if (!migrations.some(m => m.path === relativePath)) {
          const isNew = files.some(f => f.filename.includes(dir));
          if (isNew) {
            migrations.push(analyzeMigration(relativePath, sqlFile));
          }
        }
      }
    }
  }

  return migrations;
}

function analyzeMigration(relativePath: string, fullPath: string): MigrationInfo {
  const sql = readFileSync(fullPath, 'utf-8');
  const operations = parseMigrationSQL(sql);
  const riskLevel = assessMigrationRisk(operations);
  const warnings = generateMigrationWarnings(operations);
  const rollbackComplexity = assessRollbackComplexity(operations);

  const name = relativePath.split('/')[2] || 'unknown';  // Extract migration name from path

  return {
    path: relativePath,
    name,
    sql,
    riskLevel,
    operations,
    warnings,
    rollbackComplexity
  };
}

function parseMigrationSQL(sql: string): MigrationOperation[] {
  const operations: MigrationOperation[] = [];
  const lines = sql.split('\n');

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('--')) continue;

    // CREATE TABLE
    if (trimmed.match(/CREATE TABLE/i)) {
      const tableMatch = trimmed.match(/CREATE TABLE\s+"?(\w+)"?/i);
      const table = tableMatch ? tableMatch[1] : 'unknown';
      operations.push({
        type: 'CREATE_TABLE',
        table,
        details: trimmed,
        destructive: false
      });
    }

    // DROP TABLE
    else if (trimmed.match(/DROP TABLE/i)) {
      const tableMatch = trimmed.match(/DROP TABLE\s+"?(\w+)"?/i);
      const table = tableMatch ? tableMatch[1] : 'unknown';
      operations.push({
        type: 'DROP_TABLE',
        table,
        details: trimmed,
        destructive: true
      });
    }

    // ALTER TABLE ADD COLUMN
    else if (trimmed.match(/ALTER TABLE.*ADD COLUMN/i)) {
      const tableMatch = trimmed.match(/ALTER TABLE\s+"?(\w+)"?/i);
      const table = tableMatch ? tableMatch[1] : 'unknown';
      const notNull = trimmed.includes('NOT NULL');
      const hasDefault = trimmed.includes('DEFAULT');

      operations.push({
        type: 'ADD_COLUMN',
        table,
        details: trimmed,
        destructive: notNull && !hasDefault  // Dangerous if NOT NULL without DEFAULT
      });
    }

    // ALTER TABLE DROP COLUMN
    else if (trimmed.match(/ALTER TABLE.*DROP COLUMN/i)) {
      const tableMatch = trimmed.match(/ALTER TABLE\s+"?(\w+)"?/i);
      const table = tableMatch ? tableMatch[1] : 'unknown';
      operations.push({
        type: 'DROP_COLUMN',
        table,
        details: trimmed,
        destructive: true
      });
    }

    // ALTER TABLE ALTER COLUMN
    else if (trimmed.match(/ALTER TABLE.*ALTER COLUMN/i)) {
      const tableMatch = trimmed.match(/ALTER TABLE\s+"?(\w+)"?/i);
      const table = tableMatch ? tableMatch[1] : 'unknown';
      const typeChange = trimmed.includes('TYPE');

      operations.push({
        type: 'ALTER_COLUMN',
        table,
        details: trimmed,
        destructive: typeChange  // Type changes can be destructive
      });
    }

    // CREATE INDEX
    else if (trimmed.match(/CREATE.*INDEX/i)) {
      const tableMatch = trimmed.match(/ON\s+"?(\w+)"?/i);
      const table = tableMatch ? tableMatch[1] : 'unknown';
      operations.push({
        type: 'CREATE_INDEX',
        table,
        details: trimmed,
        destructive: false
      });
    }

    // ADD CONSTRAINT
    else if (trimmed.match(/ADD CONSTRAINT/i)) {
      const tableMatch = trimmed.match(/ALTER TABLE\s+"?(\w+)"?/i);
      const table = tableMatch ? tableMatch[1] : 'unknown';
      operations.push({
        type: 'ADD_CONSTRAINT',
        table,
        details: trimmed,
        destructive: false  // Usually safe, but can fail if data doesn't meet constraint
      });
    }
  }

  return operations;
}

function assessMigrationRisk(operations: MigrationOperation[]): 'high' | 'medium' | 'low' {
  const hasDestructive = operations.some(op => op.destructive);
  const hasDropTable = operations.some(op => op.type === 'DROP_TABLE');
  const hasDropColumn = operations.some(op => op.type === 'DROP_COLUMN');
  const hasTypeChange = operations.some(op =>
    op.type === 'ALTER_COLUMN' && op.details.includes('TYPE')
  );

  if (hasDropTable || hasDropColumn || hasTypeChange) return 'high';
  if (hasDestructive) return 'medium';

  // Check for potentially risky operations
  const hasAddNotNull = operations.some(op =>
    op.type === 'ADD_COLUMN' && op.details.includes('NOT NULL') && !op.details.includes('DEFAULT')
  );

  if (hasAddNotNull) return 'medium';

  return 'low';
}

function generateMigrationWarnings(operations: MigrationOperation[]): string[] {
  const warnings: string[] = [];

  for (const op of operations) {
    switch (op.type) {
      case 'DROP_TABLE':
        warnings.push(`⚠️  DROP TABLE "${op.table}" will permanently delete all data`);
        break;

      case 'DROP_COLUMN':
        warnings.push(`⚠️  DROP COLUMN will permanently delete data in that column`);
        break;

      case 'ALTER_COLUMN':
        if (op.details.includes('TYPE')) {
          warnings.push(`⚠️  Column type change may fail or lose data if incompatible`);
        }
        break;

      case 'ADD_COLUMN':
        if (op.details.includes('NOT NULL') && !op.details.includes('DEFAULT')) {
          warnings.push(`⚠️  Adding NOT NULL column without DEFAULT may fail on existing data`);
        }
        break;

      case 'CREATE_INDEX':
        warnings.push(`ℹ️  Creating index may take time on large tables`);
        break;
    }
  }

  return warnings;
}

function assessRollbackComplexity(operations: MigrationOperation[]): 'easy' | 'medium' | 'hard' | 'impossible' {
  const hasDropTable = operations.some(op => op.type === 'DROP_TABLE');
  const hasDropColumn = operations.some(op => op.type === 'DROP_COLUMN');

  // Data deletion is impossible to rollback without backups
  if (hasDropTable || hasDropColumn) return 'impossible';

  const hasTypeChange = operations.some(op =>
    op.type === 'ALTER_COLUMN' && op.details.includes('TYPE')
  );

  // Type changes are hard to rollback
  if (hasTypeChange) return 'hard';

  const hasConstraints = operations.some(op => op.type === 'ADD_CONSTRAINT');
  if (hasConstraints) return 'medium';

  // Simple additions (tables, columns, indexes) are easy to rollback
  return 'easy';
}
