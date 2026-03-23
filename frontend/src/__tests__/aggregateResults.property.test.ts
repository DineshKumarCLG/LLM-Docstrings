/**
 * Property-based tests for aggregateFunctionResults.
 *
 * Validates: Requirements 5.1, 5.3, 6.1, 6.2, 6.3, 6.4
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { aggregateFunctionResults } from "../lib/aggregateResults";
import type { BCVCategory, Claim, ClaimGroup, Violation } from "../types";

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

/** All valid BCVCategory values. */
const ALL_CATEGORIES: BCVCategory[] = ["RSV", "PCV", "SEV", "ECV", "COV", "CCV"];

/** Arbitrary that produces any valid BCVCategory. */
const arbBCVCategory: fc.Arbitrary<BCVCategory> = fc.constantFrom(...ALL_CATEGORIES);

/** Arbitrary that produces a valid Claim object. */
const arbClaim: fc.Arbitrary<Claim> = fc.record({
  id: fc.uuid(),
  category: arbBCVCategory,
  subject: fc.string({ minLength: 1, maxLength: 50 }),
  predicateObject: fc.string({ minLength: 1, maxLength: 100 }),
  conditionality: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
  sourceLine: fc.integer({ min: 1, max: 10000 }),
  rawText: fc.string({ minLength: 1, maxLength: 200 }),
});

/**
 * Arbitrary that produces a ClaimGroup with a given function name.
 * Claims count is between 0 and 5.
 */
const arbClaimGroupWithName = (functionName: string): fc.Arbitrary<ClaimGroup> =>
  fc.record({
    functionName: fc.constant(functionName),
    functionSignature: fc.string({ minLength: 1, maxLength: 100 }),
    docstring: fc.option(fc.string({ minLength: 1, maxLength: 200 }), { nil: null }),
    source: fc.string({ maxLength: 500 }),
    lineno: fc.integer({ min: 1, max: 10000 }),
    claims: fc.array(arbClaim, { minLength: 0, maxLength: 5 }),
  });

/**
 * Arbitrary that produces an array of ClaimGroups with unique function names.
 * Generates 1–6 groups.
 */
const arbClaimGroups: fc.Arbitrary<ClaimGroup[]> = fc
  .uniqueArray(
    fc.string({ minLength: 1, maxLength: 30 }).filter((s) => /^[a-zA-Z_]\w*$/.test(s)),
    { minLength: 1, maxLength: 6 },
  )
  .chain((names) =>
    fc.tuple(...names.map((name) => arbClaimGroupWithName(name))),
  )
  .map((groups) => Array.from(groups));


// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

describe("aggregateFunctionResults — property tests", () => {
  /**
   * Property 7: Aggregation Completeness
   *
   * For any set of claim groups, aggregateFunctionResults produces exactly one
   * FunctionVerificationResult per unique function name present in the claim groups.
   *
   * **Validates: Requirements 5.1, 6.1**
   */
  it("Property 7: Aggregation Completeness — one result per unique function in claim groups", () => {
    fc.assert(
      fc.property(arbClaimGroups, (claimGroups) => {
        const results = aggregateFunctionResults([], claimGroups);

        // Exactly one result per unique function name
        expect(results).toHaveLength(claimGroups.length);

        const resultNames = new Set(results.map((r) => r.functionName));
        const groupNames = new Set(claimGroups.map((g) => g.functionName));
        expect(resultNames).toEqual(groupNames);
      }),
    );
  });

  /**
   * Property 8: Aggregation Count Invariant
   *
   * For any FunctionVerificationResult, passCount + failCount equals the total
   * number of claims for that function.
   *
   * **Validates: Requirement 6.2**
   */
  it("Property 8: Aggregation Count Invariant — passCount + failCount equals total claims per function", () => {
    fc.assert(
      fc.property(arbClaimGroups, (claimGroups) => {
        // Build violations referencing functions from the groups
        const claimCountByName = new Map(
          claimGroups.map((g) => [g.functionName, g.claims.length]),
        );

        // Generate violations: at most claimCount violations per function
        const violations: Violation[] = claimGroups.flatMap((g) => {
          const count = Math.min(g.claims.length, Math.floor(g.claims.length / 2));
          return Array.from({ length: count }, (_, i): Violation => ({
            functionId: `fn-${i}`,
            functionName: g.functionName,
            claim: g.claims[i] ?? {
              id: `c-${i}`,
              category: "RSV" as BCVCategory,
              subject: "x",
              predicateObject: "y",
              conditionality: null,
              sourceLine: 1,
              rawText: "x y",
            },
            testCode: "assert False",
            outcome: "fail" as const,
            traceback: null,
            expected: null,
            actual: null,
          }));
        });

        const results = aggregateFunctionResults(violations, claimGroups);

        for (const result of results) {
          const totalClaims = claimCountByName.get(result.functionName) ?? 0;
          expect(result.passCount + result.failCount).toBe(totalClaims);
        }
      }),
    );
  });

  /**
   * Property 9: Aggregation Immutability
   *
   * Calling aggregateFunctionResults does not mutate the input violations or
   * claim groups arrays (lengths and contents remain identical before and after).
   *
   * **Validates: Requirement 6.3**
   */
  it("Property 9: Aggregation Immutability — input arrays not mutated", () => {
    fc.assert(
      fc.property(arbClaimGroups, (claimGroups) => {
        const violations: Violation[] = claimGroups.slice(0, 2).map((g, i) => ({
          functionId: `fn-${i}`,
          functionName: g.functionName,
          claim: {
            id: `c-${i}`,
            category: "RSV" as BCVCategory,
            subject: "x",
            predicateObject: "y",
            conditionality: null,
            sourceLine: 1,
            rawText: "x y",
          },
          testCode: "assert False",
          outcome: "fail" as const,
          traceback: null,
          expected: null,
          actual: null,
        }));

        // Snapshot before
        const violationsBefore = JSON.stringify(violations);
        const groupsBefore = JSON.stringify(claimGroups);

        aggregateFunctionResults(violations, claimGroups);

        // Snapshot after — must be identical
        expect(JSON.stringify(violations)).toBe(violationsBefore);
        expect(JSON.stringify(claimGroups)).toBe(groupsBefore);
      }),
    );
  });

  /**
   * Property 10: Aggregation Status Derivation
   *
   * For any FunctionVerificationResult:
   * - status is "no-claims"    when claims.length === 0
   * - status is "all-pass"     when failCount === 0 and claims.length > 0
   * - status is "has-failures" when failCount > 0
   *
   * **Validates: Requirement 6.4**
   */
  it("Property 10: Aggregation Status Derivation — correct status assignment based on failCount", () => {
    fc.assert(
      fc.property(arbClaimGroups, (claimGroups) => {
        // Build violations: one per function that has at least one claim
        const violations: Violation[] = claimGroups
          .filter((g) => g.claims.length > 0)
          .slice(0, Math.ceil(claimGroups.length / 2))
          .map((g, i) => ({
            functionId: `fn-${i}`,
            functionName: g.functionName,
            claim: g.claims[0]!,
            testCode: "assert False",
            outcome: "fail" as const,
            traceback: null,
            expected: null,
            actual: null,
          }));

        const violatedFunctions = new Set(violations.map((v) => v.functionName));
        const results = aggregateFunctionResults(violations, claimGroups);

        for (const result of results) {
          const claimCount = claimGroups.find(
            (g) => g.functionName === result.functionName,
          )!.claims.length;

          if (claimCount === 0) {
            expect(result.status).toBe("no-claims");
          } else if (violatedFunctions.has(result.functionName)) {
            expect(result.status).toBe("has-failures");
            expect(result.failCount).toBeGreaterThan(0);
          } else {
            expect(result.status).toBe("all-pass");
            expect(result.failCount).toBe(0);
          }
        }
      }),
    );
  });

  /**
   * Property 11: Function Results Sort Order
   *
   * The output of aggregateFunctionResults is sorted by failCount in descending
   * order: each element's failCount >= the next element's failCount.
   *
   * **Validates: Requirement 5.3**
   */
  it("Property 11: Function Results Sort Order — sorted by failCount descending", () => {
    fc.assert(
      fc.property(arbClaimGroups, (claimGroups) => {
        // Assign varying violation counts to create interesting sort scenarios
        const violations: Violation[] = claimGroups.flatMap((g, groupIdx) => {
          const count = Math.min(g.claims.length, groupIdx % 3);
          return Array.from({ length: count }, (_, i) => ({
            functionId: `fn-${groupIdx}-${i}`,
            functionName: g.functionName,
            claim: g.claims[i] ?? {
              id: `c-${groupIdx}-${i}`,
              category: "RSV" as BCVCategory,
              subject: "x",
              predicateObject: "y",
              conditionality: null,
              sourceLine: 1,
              rawText: "x y",
            },
            testCode: "assert False",
            outcome: "fail" as const,
            traceback: null,
            expected: null,
            actual: null,
          }));
        });

        const results = aggregateFunctionResults(violations, claimGroups);

        for (let i = 0; i < results.length - 1; i++) {
          expect(results[i]!.failCount).toBeGreaterThanOrEqual(results[i + 1]!.failCount);
        }
      }),
    );
  });
});
