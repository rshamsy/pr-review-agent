# Developer Guide: Writing Tests in HubTrack

This guide explains how to write tests for the HubTrack codebase using Vitest.

## Quick Start

```bash
# Run tests in watch mode while developing
npm test

# Run all tests once (same as CI)
npm run test:run

# See visual test results
npm run test:ui

# Generate coverage report
npm run test:coverage
```

---

## Where to Put Tests

```
tests/
└── lib/
    └── services/
        ├── receipt-service.test.ts      # Tests for receipt-service.ts
        ├── bale-production-service.test.ts
        └── hub-dashboard.test.ts
```

**Rule:** Mirror your source file path. If you create `lib/services/my-feature.ts`, create `tests/lib/services/my-feature.test.ts`.

---

## Test File Template

Copy this template when creating a new test file:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { myFunction } from '@/lib/services/my-service';
import prisma from '@/lib/prisma';

describe('My Service', () => {
  // Reset mocks before each test
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('myFunction', () => {
    it('should do the expected thing', async () => {
      // 1. ARRANGE - Set up test data and mocks
      vi.mocked(prisma.user.findUnique).mockResolvedValue({
        id: 'user1',
        name: 'Test User'
      } as any);

      // 2. ACT - Call the function being tested
      const result = await myFunction({ userId: 'user1' });

      // 3. ASSERT - Verify the result
      expect(result).toBeDefined();
      expect(result.name).toBe('Test User');
    });

    it('should throw error when user not found', async () => {
      // ARRANGE
      vi.mocked(prisma.user.findUnique).mockResolvedValue(null);

      // ACT & ASSERT
      await expect(
        myFunction({ userId: 'nonexistent' })
      ).rejects.toThrow('User not found');
    });
  });
});
```

---

## Key Concepts

### 1. Mocking Prisma

Prisma is already mocked globally in `tests/setup.ts`. Just use `vi.mocked()`:

```typescript
// Mock a successful query
vi.mocked(prisma.vehicle.findUnique).mockResolvedValue({
  id: 1,
  vehicleNumber: 'ABC123'
} as any);

// Mock an empty result
vi.mocked(prisma.vehicle.findMany).mockResolvedValue([]);

// Mock a database error
vi.mocked(prisma.vehicle.create).mockRejectedValue(
  new Error('Database connection failed')
);
```

### 2. Testing Transactions

```typescript
vi.mocked(prisma.$transaction).mockImplementation(async (callback: any) => {
  const mockTx = {
    materialReceipt: {
      create: vi.fn(() => ({ id: 1 })),
    },
  };
  return callback(mockTx);
});
```

### 3. Test Organization

Use nested `describe` blocks to group related tests:

```typescript
describe('Receipt Service', () => {
  describe('createReceipt', () => {
    describe('weight calculations', () => {
      it('should calculate net weight correctly', ...);
      it('should handle zero weights', ...);
    });

    describe('validation', () => {
      it('should reject empty bag entries', ...);
      it('should require vehicle ID', ...);
    });
  });
});
```

---

## What to Test

| DO Test | DON'T Test |
|---------|------------|
| Business logic calculations | Prisma itself |
| Validation rules | Next.js framework code |
| Error handling | UI components (for now) |
| Edge cases (nulls, empty arrays) | Third-party libraries |
| Conditional logic branches | Simple getters/setters |

---

## Common Patterns in This Codebase

### Testing Calculations

```typescript
it('should calculate net good weight (good - empty)', async () => {
  // Test that 100 good - 10 empty = 90 net
  const mockReceipt = {
    id: 1,
    receiptSummary: {
      totalGoodWeight: 100,
      totalEmptyWeight: 10,
      netGoodWeight: 90,
    },
  };
  vi.mocked(prisma.$transaction).mockResolvedValue(mockReceipt as any);

  const result = await createReceipt({
    vehicleId: 1,
    bagEntries: [
      { type: 'good', weight: 100 },
      { type: 'empty', weight: 10 },
    ],
  });

  expect(result.receiptSummary.netGoodWeight).toBe(90);
});
```

### Testing Validation

```typescript
it('should throw error when no bag entries provided', async () => {
  await expect(
    createReceipt({
      vehicleId: 1,
      submittedById: 'user1',
      bagEntries: []
    })
  ).rejects.toThrow('At least one bag entry is required.');
});
```

### Testing Function Calls

```typescript
it('should query trip with routePickups included', async () => {
  vi.mocked(prisma.user.findUnique).mockResolvedValue({ id: 'user1' } as any);
  vi.mocked(prisma.trip.findUnique).mockResolvedValue({ id: 1 } as any);
  vi.mocked(prisma.$transaction).mockResolvedValue({ id: 1 } as any);

  await createReceipt({
    tripId: 1,
    vehicleId: 1,
    submittedById: 'user1',
    bagEntries: [{ type: 'good', weight: 50 }],
  });

  expect(prisma.trip.findUnique).toHaveBeenCalledWith({
    where: { id: 1 },
    include: { routePickups: true },
  });
});
```

---

## PR Checklist for Tests

Before submitting a PR, verify:

- [ ] Tests exist for new business logic
- [ ] All tests pass locally (`npm run test:run`)
- [ ] Edge cases are covered (empty inputs, nulls, errors)
- [ ] Test names clearly describe what's being tested
- [ ] Mocks are reset with `vi.clearAllMocks()` in `beforeEach`

---

## Adding New Prisma Models to Mocks

If you add a new Prisma model, update `tests/setup.ts`:

```typescript
vi.mock('@/lib/prisma', () => ({
  default: {
    // ... existing models ...
    yourNewModel: {
      create: vi.fn(),
      findMany: vi.fn(),
      findUnique: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
    },
  },
}));
```

---

## Running Tests in CI

Tests run automatically on every PR via GitHub Actions. The CI pipeline:

1. Runs `npm run test:run`
2. Fails the PR if any test fails
3. Shows test output in the GitHub Actions logs

See `.github/workflows/pr-checks.yml` for the full CI configuration.

---

## Debugging Failed Tests

### Using the UI

```bash
npm run test:ui
```

This opens an interactive browser interface where you can:
- See all tests and their status
- Re-run individual tests
- View detailed error messages

### Verbose Output

```bash
npm test -- --reporter=verbose
```

### Run a Single Test File

```bash
npm test -- tests/lib/services/receipt-service.test.ts
```

### Run Tests Matching a Pattern

```bash
npm test -- -t "weight calculation"
```

---

## Resources

- [Vitest Documentation](https://vitest.dev/)
- [Testing Library](https://testing-library.com/)
- Project test examples: `tests/lib/services/`
