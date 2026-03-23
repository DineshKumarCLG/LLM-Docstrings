/**
 * Property-based tests for deriveStageStates.
 *
 * Validates: Requirements 10.1, 10.2
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { deriveStageStates } from "../lib/pipelineUtils";
import type { AnalysisStatus } from "../types";

/** All valid AnalysisStatus values. */
const ALL_STATUSES: AnalysisStatus[] = [
  "pending",
  "bce_running",
  "bce_complete",
  "dts_running",
  "dts_complete",
  "rv_running",
  "complete",
  "failed",
];

/** Arbitrary that produces any valid AnalysisStatus. */
const arbAnalysisStatus: fc.Arbitrary<AnalysisStatus> = fc.constantFrom(
  ...ALL_STATUSES,
);

/**
 * Pipeline progression order (excludes "failed" which is a terminal state,
 * not part of the linear progression).
 */
const STATUS_PROGRESSION: AnalysisStatus[] = [
  "pending",
  "bce_running",
  "bce_complete",
  "dts_running",
  "dts_complete",
  "rv_running",
  "complete",
];

/**
 * Arbitrary that produces a pair of statuses (earlier, later) from the
 * pipeline progression where earlier comes strictly before later.
 */
const arbStatusPairOrdered: fc.Arbitrary<[AnalysisStatus, AnalysisStatus]> =
  fc
    .tuple(
      fc.integer({ min: 0, max: STATUS_PROGRESSION.length - 1 }),
      fc.integer({ min: 0, max: STATUS_PROGRESSION.length - 1 }),
    )
    .filter(([a, b]) => a < b)
    .map(([a, b]) => [STATUS_PROGRESSION[a]!, STATUS_PROGRESSION[b]!]);

describe("deriveStageStates — property tests", () => {
  /**
   * Property 3: Stage Derivation Count
   *
   * For any valid AnalysisStatus, deriveStageStates returns exactly 3 entries.
   *
   * **Validates: Requirements 10.1**
   */
  it("Property 3: Stage Derivation Count — always returns exactly 3 entries", () => {
    fc.assert(
      fc.property(arbAnalysisStatus, (status) => {
        const stages = deriveStageStates(status);
        expect(stages).toHaveLength(3);
      }),
    );
  });

  /**
   * Property 4: Stage Completion Monotonicity
   *
   * For any pair of statuses where one is later in the pipeline sequence,
   * the set of completed stages for the later status is a superset of the
   * completed stages for the earlier status.
   *
   * **Validates: Requirements 10.2**
   */
  it("Property 4: Stage Completion Monotonicity — completed stages only grow as status advances", () => {
    fc.assert(
      fc.property(arbStatusPairOrdered, ([earlier, later]) => {
        const earlierStages = deriveStageStates(earlier);
        const laterStages = deriveStageStates(later);

        const completedEarlier = new Set(
          earlierStages
            .filter((s) => s.state === "complete")
            .map((s) => s.key),
        );
        const completedLater = new Set(
          laterStages
            .filter((s) => s.state === "complete")
            .map((s) => s.key),
        );

        // Every stage completed in the earlier status must also be completed
        // in the later status (monotonicity).
        for (const key of completedEarlier) {
          expect(completedLater.has(key)).toBe(true);
        }
      }),
    );
  });
});
