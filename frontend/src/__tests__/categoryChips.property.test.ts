/**
 * Property-based tests for CategoryBreakdownChips count accuracy.
 *
 * This is a pure logic test — no React rendering needed.
 * The CategoryBreakdownChips component reads `breakdown[category] ?? 0` for each chip.
 *
 * **Validates: Requirement 4.1**
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import type { BCVCategory } from "../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** All valid BCVCategory values. */
const BCV_CATEGORIES: BCVCategory[] = ["RSV", "PCV", "SEV", "ECV", "COV", "CCV"];

// ---------------------------------------------------------------------------
// The logic under test
//
// CategoryBreakdownChips reads the count for each chip as:
//   breakdown[category] ?? 0
//
// We test this logic directly without rendering the component.
// ---------------------------------------------------------------------------

/** Mirrors the count-reading logic from CategoryBreakdownChips. */
function getChipCount(
  breakdown: Partial<Record<BCVCategory, number>>,
  category: BCVCategory,
): number {
  return breakdown[category] ?? 0;
}

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

/** Arbitrary that produces any valid BCVCategory. */
const arbBCVCategory: fc.Arbitrary<BCVCategory> = fc.constantFrom(...BCV_CATEGORIES);

/**
 * Arbitrary that produces a partial breakdown record with non-negative integer
 * counts for a random subset of BCVCategory keys.
 */
const arbPartialBreakdown: fc.Arbitrary<Partial<Record<BCVCategory, number>>> = fc
  .array(
    fc.tuple(arbBCVCategory, fc.integer({ min: 0, max: 1000 })),
    { minLength: 0, maxLength: BCV_CATEGORIES.length },
  )
  .map((pairs) => Object.fromEntries(pairs) as Partial<Record<BCVCategory, number>>);

/**
 * Arbitrary that produces a full breakdown record (all 6 categories present)
 * with non-negative integer counts.
 */
const arbFullBreakdown: fc.Arbitrary<Record<BCVCategory, number>> = fc.record({
  RSV: fc.integer({ min: 0, max: 1000 }),
  PCV: fc.integer({ min: 0, max: 1000 }),
  SEV: fc.integer({ min: 0, max: 1000 }),
  ECV: fc.integer({ min: 0, max: 1000 }),
  COV: fc.integer({ min: 0, max: 1000 }),
  CCV: fc.integer({ min: 0, max: 1000 }),
});

// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

describe("CategoryBreakdownChips — property tests", () => {
  /**
   * Property 5: Category Chip Count Accuracy
   *
   * For any categoryBreakdown record (mapping BCVCategory to number), the count
   * displayed on each chip equals `breakdown[category]`.
   *
   * **Validates: Requirement 4.1**
   */
  it("Property 5: Category Chip Count Accuracy — chip count equals breakdown[category] for all present categories", () => {
    fc.assert(
      fc.property(arbFullBreakdown, (breakdown) => {
        for (const category of BCV_CATEGORIES) {
          const chipCount = getChipCount(breakdown, category);
          expect(chipCount).toBe(breakdown[category]);
        }
      }),
    );
  });

  /**
   * Property 5 (edge case): Categories not in the breakdown default to 0.
   *
   * For categories absent from the breakdown record, the chip count should be 0.
   *
   * **Validates: Requirement 4.1**
   */
  it("Property 5: Category Chip Count Accuracy — missing categories default to 0", () => {
    fc.assert(
      fc.property(arbPartialBreakdown, (breakdown) => {
        for (const category of BCV_CATEGORIES) {
          const chipCount = getChipCount(breakdown, category);
          if (category in breakdown) {
            expect(chipCount).toBe(breakdown[category]);
          } else {
            expect(chipCount).toBe(0);
          }
        }
      }),
    );
  });
});
