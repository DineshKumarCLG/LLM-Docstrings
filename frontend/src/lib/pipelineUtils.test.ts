import { describe, it, expect } from "vitest";
import { deriveStageStates } from "./pipelineUtils";
import type { AnalysisStatus } from "../types";

describe("deriveStageStates", () => {
  it("returns exactly 3 entries for every valid status", () => {
    const statuses: AnalysisStatus[] = [
      "pending", "bce_running", "bce_complete",
      "dts_running", "dts_complete", "rv_running",
      "complete", "failed",
    ];
    for (const s of statuses) {
      expect(deriveStageStates(s)).toHaveLength(3);
    }
  });

  it("returns all pending for 'pending' status", () => {
    const states = deriveStageStates("pending");
    expect(states.map((s) => s.state)).toEqual(["pending", "pending", "pending"]);
  });

  it("returns BCE active, others pending for 'bce_running'", () => {
    const states = deriveStageStates("bce_running");
    expect(states.map((s) => s.state)).toEqual(["active", "pending", "pending"]);
  });

  it("returns BCE complete, others pending for 'bce_complete'", () => {
    const states = deriveStageStates("bce_complete");
    expect(states.map((s) => s.state)).toEqual(["complete", "pending", "pending"]);
  });

  it("returns BCE complete, DTS active, RV pending for 'dts_running'", () => {
    const states = deriveStageStates("dts_running");
    expect(states.map((s) => s.state)).toEqual(["complete", "active", "pending"]);
  });

  it("returns BCE+DTS complete, RV pending for 'dts_complete'", () => {
    const states = deriveStageStates("dts_complete");
    expect(states.map((s) => s.state)).toEqual(["complete", "complete", "pending"]);
  });

  it("returns BCE+DTS complete, RV active for 'rv_running'", () => {
    const states = deriveStageStates("rv_running");
    expect(states.map((s) => s.state)).toEqual(["complete", "complete", "active"]);
  });

  it("returns all complete for 'complete' status", () => {
    const states = deriveStageStates("complete");
    expect(states.map((s) => s.state)).toEqual(["complete", "complete", "complete"]);
  });

  it("returns all failed for 'failed' status", () => {
    const states = deriveStageStates("failed");
    expect(states.map((s) => s.state)).toEqual(["failed", "failed", "failed"]);
  });

  it("preserves stage keys in order: bce, dts, rv", () => {
    const states = deriveStageStates("pending");
    expect(states.map((s) => s.key)).toEqual(["bce", "dts", "rv"]);
  });

  it("spreads full StageConfig properties into each StageState", () => {
    const states = deriveStageStates("bce_running");
    expect(states[0]).toMatchObject({
      key: "bce",
      label: "BCE",
      fullName: "Behavioral Claim Extractor",
      state: "active",
    });
  });
});
