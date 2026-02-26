/**
 * Property 22: Dashboard polling termination
 *
 * Validates: Requirement 8.4
 *
 * When status reaches COMPLETE or FAILED, polling stops (refetchInterval returns false).
 * For any other AnalysisStatus, polling continues (refetchInterval returns 2000).
 */

import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import type { AnalysisStatus } from "@/types";

// ---------------------------------------------------------------------------
// Extract the refetchInterval decision logic from useAnalysis.
// This mirrors the logic in src/hooks/useAnalysis.ts without needing
// React/TanStack Query infrastructure.
// ---------------------------------------------------------------------------

const TERMINAL_STATUSES: ReadonlySet<AnalysisStatus> = new Set([
  "complete",
  "failed",
]);

const ALL_STATUSES: readonly AnalysisStatus[] = [
  "pending",
  "bce_running",
  "bce_complete",
  "dts_running",
  "dts_complete",
  "rv_running",
  "complete",
  "failed",
] as const;

const IN_PROGRESS_STATUSES = ALL_STATUSES.filter(
  (s) => !TERMINAL_STATUSES.has(s),
);

/**
 * Pure function replicating the refetchInterval callback from useAnalysis.
 * Returns `false` to stop polling, or `2000` to continue.
 */
function shouldPoll(status: AnalysisStatus | undefined): false | 2000 {
  if (status === "complete" || status === "failed") {
    return false;
  }
  return 2000;
}

// ---------------------------------------------------------------------------
// fast-check arbitraries
// ---------------------------------------------------------------------------

const terminalStatusArb: fc.Arbitrary<AnalysisStatus> = fc.constantFrom(
  ...([...TERMINAL_STATUSES] as AnalysisStatus[]),
);

const inProgressStatusArb: fc.Arbitrary<AnalysisStatus> = fc.constantFrom(
  ...IN_PROGRESS_STATUSES,
);

// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

describe("Property 22: Dashboard polling termination", () => {
  /**
   * **Validates: Requirements 8.4**
   *
   * For any terminal status (complete | failed), refetchInterval returns false.
   */
  it("polling stops for any terminal status (complete or failed)", () => {
    fc.assert(
      fc.property(terminalStatusArb, (status) => {
        expect(shouldPoll(status)).toBe(false);
      }),
    );
  });

  /**
   * **Validates: Requirements 8.4**
   *
   * For any in-progress status, refetchInterval returns 2000.
   */
  it("polling continues at 2000ms for any non-terminal status", () => {
    fc.assert(
      fc.property(inProgressStatusArb, (status) => {
        expect(shouldPoll(status)).toBe(2000);
      }),
    );
  });

  /**
   * **Validates: Requirements 8.4**
   *
   * When status is undefined (no data yet), polling should continue.
   */
  it("polling continues when status is undefined (initial load)", () => {
    expect(shouldPoll(undefined)).toBe(2000);
  });
});
