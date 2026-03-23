/**
 * Property-based tests for category filter consistency in PerFunctionResults.
 *
 * This is a pure logic test — no React rendering needed.
 * The filtering logic is extracted directly from PerFunctionResults.tsx and
 * tested against arbitrary inputs.
 *
 * **Validates: Requirements 4.2, 5.5**
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import type {
  BCVCategory,
  FunctionVerificationResult,
  Violation,
  Claim,
} from "../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BCV_CATEGORIES: BCVCategory[] = ["RSV", "PCV", "SEV", "ECV", "COV", "CCV"];

// ---------------------------------------------------------------------------
// The logic under test
//
// Extracted from PerFunctionResults.tsx — the category filter branch:
//
//   if (categoryFilter !== "all") {
//     results = results
//       .map((r) => ({
//         ...r,
//         violations: r.violations.filter((v) => v.claim.category === categoryFilter),
//         claims: r.claims.filter(
//           (c) =>
//             !r.violations.some((v) => v.claim.id === c.id) ||
//             c.category === categoryFilter,
//         ),
//       }))
//       .filter((r) => r.violations.length > 0);
//   }
// ---------------------------------------------------------------------------

function applyCategoryFilter(
  results: FunctionVerificationResult[],
  categoryFilter: BCVCategory | "all",
): FunctionVerificationResult[] {
  if (categoryFilter === "all") return results;

  return results
    .map((r) => ({
      ...r,
      violations: r.violations.filter((v) => v.claim.category === categoryFilter),
      claims: r.claims.filter(
        (c) =>
          !r.violations.some((v) => v.claim.id === c.id) ||
          c.category === categoryFilter,
      ),
    }))
    .filter((r) => r.violations.length > 0);
}

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

/** Arbitrary that produces any valid BCVCategory (not "all"). */
const arbBCVCategory: fc.Arbitrary<BCVCategory> = fc.constantFrom(...BCV_CATEGORIES);

/** Arbitrary that produces a valid Claim with a given category. */
function arbClaim(category?: BCVCategory): fc.Arbitrary<Claim> {
  return fc.record({
    id: fc.uuid(),
    category: category !== undefined ? fc.constant(category) : arbBCVCategory,
    subject: fc.string({ minLength: 1, maxLength: 40 }),
    predicateObject: fc.string({ minLength: 1, maxLength: 80 }),
    conditionality: fc.option(fc.string({ minLength: 1, maxLength: 40 }), { nil: null }),
    sourceLine: fc.integer({ min: 1, max: 9999 }),
    rawText: fc.string({ minLength: 1, maxLength: 200 }),
  });
}

/** Arbitrary that produces a Violation whose claim has the given category. */
function arbViolation(category?: BCVCategory): fc.Arbitrary<Violation> {
  return arbClaim(category).chain((claim) =>
    fc.record({
      functionId: fc.uuid(),
      functionName: fc.string({ minLength: 1, maxLength: 40 }),
      claim: fc.constant(claim),
      testCode: fc.string({ minLength: 1, maxLength: 200 }),
      outcome: fc.constantFrom("pass", "fail", "error", "undetermined") as fc.Arbitrary<
        "pass" | "fail" | "error" | "undetermined"
      >,
      traceback: fc.option(fc.string({ minLength: 1, maxLength: 200 }), { nil: null }),
      expected: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
      actual: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
    }),
  );
}

/**
 * Arbitrary that produces a FunctionVerificationResult with violations having
 * mixed categories (so the filter has something to do).
 */
const arbFunctionVerificationResult: fc.Arbitrary<FunctionVerificationResult> = fc
  .array(arbViolation(), { minLength: 0, maxLength: 8 })
  .chain((violations) => {
    // Build claims from violations plus some extra passing claims
    const violationClaims = violations.map((v) => v.claim);
    return fc
      .array(arbClaim(), { minLength: 0, maxLength: 4 })
      .chain((extraClaims) => {
        const allClaims = [...violationClaims, ...extraClaims];
        const failCount = violations.length;
        const passCount = extraClaims.length;
        const status: "all-pass" | "has-failures" | "no-claims" =
          allClaims.length === 0
            ? "no-claims"
            : failCount > 0
              ? "has-failures"
              : "all-pass";

        return fc.record({
          functionName: fc.string({ minLength: 1, maxLength: 40 }),
          functionSignature: fc.string({ minLength: 1, maxLength: 80 }),
          claims: fc.constant(allClaims),
          violations: fc.constant(violations),
          passCount: fc.constant(passCount),
          failCount: fc.constant(failCount),
          status: fc.constant(status),
        });
      });
  });

/** Arbitrary array of FunctionVerificationResult. */
const arbResults: fc.Arbitrary<FunctionVerificationResult[]> = fc.array(
  arbFunctionVerificationResult,
  { minLength: 0, maxLength: 10 },
);

// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

describe("PerFunctionResults — category filter consistency (property tests)", () => {
  /**
   * Property 6: Category Filter Consistency
   *
   * For any active category filter (not "all") and any set of
   * FunctionVerificationResults, every violation in every result returned by
   * `applyCategoryFilter` must have `violation.claim.category` equal to the
   * active filter category.
   *
   * **Validates: Requirements 4.2, 5.5**
   */
  it("Property 6: Category Filter Consistency — all displayed violations match the active filter category", () => {
    fc.assert(
      fc.property(arbBCVCategory, arbResults, (category, results) => {
        const filtered = applyCategoryFilter(results, category);

        for (const result of filtered) {
          for (const violation of result.violations) {
            expect(violation.claim.category).toBe(category);
          }
        }
      }),
    );
  });

  /**
   * Property 6 (corollary): Results with no matching violations are excluded.
   *
   * After filtering, every result in the output must have at least one violation
   * (results with zero matching violations are dropped).
   *
   * **Validates: Requirements 4.2, 5.5**
   */
  it("Property 6: Category Filter Consistency — results with no matching violations are excluded", () => {
    fc.assert(
      fc.property(arbBCVCategory, arbResults, (category, results) => {
        const filtered = applyCategoryFilter(results, category);

        for (const result of filtered) {
          expect(result.violations.length).toBeGreaterThan(0);
        }
      }),
    );
  });

  /**
   * Property 6 (identity): "all" filter returns results unchanged.
   *
   * When categoryFilter is "all", the function must return the original array
   * reference without modification.
   *
   * **Validates: Requirements 4.2, 5.5**
   */
  it('Property 6: Category Filter Consistency — "all" filter returns results unchanged', () => {
    fc.assert(
      fc.property(arbResults, (results) => {
        const filtered = applyCategoryFilter(results, "all");
        expect(filtered).toBe(results);
      }),
    );
  });
});
