/**
 * Pipeline stage state derivation utilities.
 *
 * Requirements: 10.1, 10.2, 10.3
 */

import type { AnalysisStatus, StageState } from "../types";
import { PIPELINE_STAGES } from "./constants";

/**
 * Status progression order used to determine which stages are
 * complete, active, or pending for a given analysis status.
 */
const STATUS_ORDER: AnalysisStatus[] = [
  "pending",
  "bce_running",
  "bce_complete",
  "dts_running",
  "dts_complete",
  "rv_running",
  "complete",
];

/**
 * Derives the visual state of each pipeline stage from the current
 * analysis status.
 *
 * PRECONDITION:  status is a valid AnalysisStatus
 * POSTCONDITION: returns exactly 3 StageState entries (BCE, DTS, RV)
 *
 * @param status - Current analysis status
 * @returns Array of 3 StageState entries with derived `state` field
 */
export function deriveStageStates(status: AnalysisStatus): StageState[] {
  const currentIdx = STATUS_ORDER.indexOf(status);

  return PIPELINE_STAGES.map((stage) => {
    if (status === "failed") {
      // Since we don't know the exact failure point, mark all stages as failed.
      return { ...stage, state: "failed" as const };
    }

    const runIdx = STATUS_ORDER.indexOf(stage.runningStatus);
    const completeIdx = STATUS_ORDER.indexOf(stage.completeStatus);

    if (currentIdx >= completeIdx) {
      return { ...stage, state: "complete" as const };
    }
    if (currentIdx >= runIdx) {
      return { ...stage, state: "active" as const };
    }
    return { ...stage, state: "pending" as const };
  });
}
