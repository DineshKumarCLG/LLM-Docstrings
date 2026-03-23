/**
 * Property-based tests for Research Tab idempotency.
 *
 * The ResearchTab is purely static — it uses only BCV_TAXONOMY and
 * PYBCV_420_STATS constants and makes no API calls. These tests verify
 * that the underlying static data is stable and deterministic regardless
 * of any external input (e.g., analysis ID).
 *
 * **Validates: Requirement 9.6**
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { BCV_TAXONOMY, PYBCV_420_STATS } from "../lib/constants";

/** The 6 expected BCV category codes in canonical order. */
const EXPECTED_CATEGORIES = ["RSV", "PCV", "SEV", "ECV", "COV", "CCV"] as const;

describe("ResearchTab static data — property tests", () => {
  /**
   * Property 14a: Content is independent of analysis ID
   *
   * For any arbitrary string used as an analysis ID, the static data
   * (BCV_TAXONOMY, PYBCV_420_STATS) remains unchanged — accessing the
   * constants multiple times always yields the same reference/values.
   *
   * **Validates: Requirement 9.6**
   */
  it("Property 14a: Content is independent of analysis ID", () => {
    fc.assert(
      fc.property(fc.string(), (_analysisId) => {
        // Simulate what ResearchTab does: read the static constants.
        // The constants must be identical regardless of the analysis ID.
        const taxonomy = BCV_TAXONOMY;
        const stats = PYBCV_420_STATS;

        expect(taxonomy).toBe(BCV_TAXONOMY);
        expect(stats).toBe(PYBCV_420_STATS);
        expect(taxonomy.length).toBe(6);
        expect(stats.totalInstances).toBe(420);
      }),
    );
  });

  /**
   * Property 14b: BCV_TAXONOMY is stable
   *
   * The taxonomy array always has exactly 6 entries with the same
   * categories in the same order.
   *
   * **Validates: Requirement 9.6**
   */
  it("Property 14b: BCV_TAXONOMY is stable — 6 entries in canonical order", () => {
    fc.assert(
      // Use a counter arbitrary to simulate multiple "accesses"
      fc.property(fc.integer({ min: 1, max: 100 }), (_accessCount) => {
        const taxonomy = BCV_TAXONOMY;

        expect(taxonomy).toHaveLength(6);

        EXPECTED_CATEGORIES.forEach((category, index) => {
          expect(taxonomy[index]!.category).toBe(category);
        });
      }),
    );
  });

  /**
   * Property 14c: PYBCV_420_STATS is stable
   *
   * The benchmark stats always have the same values regardless of when
   * accessed.
   *
   * **Validates: Requirement 9.6**
   */
  it("Property 14c: PYBCV_420_STATS is stable — same values on every access", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 100 }), (_accessCount) => {
        const stats = PYBCV_420_STATS;

        expect(stats.totalInstances).toBe(420);
        expect(stats.categories).toBe(6);
        expect(stats.llmsTested).toBe(3);
        expect(stats.llmNames).toHaveLength(3);
      }),
    );
  });

  /**
   * Property 14d: Category distribution sums to totalInstances
   *
   * The sum of all category counts in categoryDistribution equals
   * totalInstances (420).
   *
   * **Validates: Requirement 9.6**
   */
  it("Property 14d: Category distribution sums to totalInstances", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 100 }), (_accessCount) => {
        const stats = PYBCV_420_STATS;
        const total = Object.values(stats.categoryDistribution).reduce(
          (sum, count) => sum + count,
          0,
        );

        expect(total).toBe(stats.totalInstances);
      }),
    );
  });

  /**
   * Property 14e: Detection rates are in [0, 1]
   *
   * All detection rates in PYBCV_420_STATS are valid probabilities
   * (between 0 and 1 inclusive).
   *
   * **Validates: Requirement 9.6**
   */
  it("Property 14e: Detection rates are valid probabilities in [0, 1]", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 100 }), (_accessCount) => {
        const stats = PYBCV_420_STATS;

        for (const rate of Object.values(stats.detectionRates)) {
          expect(rate).toBeGreaterThanOrEqual(0);
          expect(rate).toBeLessThanOrEqual(1);
        }
      }),
    );
  });
});
