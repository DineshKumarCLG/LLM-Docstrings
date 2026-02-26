/**
 * TypeScript types mirroring backend Pydantic schemas.
 *
 * Requirements: 8.1, 8.2
 */

// ---------------------------------------------------------------------------
// Enums (string literal unions for type safety)
// ---------------------------------------------------------------------------

/** Six-category BCV taxonomy from the VeriDoc paper. */
export type BCVCategory = "RSV" | "PCV" | "SEV" | "ECV" | "COV" | "CCV";

/** Pipeline execution status, following the stage transition sequence. */
export type AnalysisStatus =
  | "pending"
  | "bce_running"
  | "bce_complete"
  | "dts_running"
  | "dts_complete"
  | "rv_running"
  | "complete"
  | "failed";

/** Outcome classification for a single synthesized test execution. */
export type TestOutcome = "pass" | "fail" | "error" | "undetermined";

/** Supported LLM providers. */
export type LLMProvider = "gpt-4.1-mini" | "claude-sonnet-4-20250514" | "gemini-3-flash-preview" | "bedrock";

// ---------------------------------------------------------------------------
// Category metadata
// ---------------------------------------------------------------------------

/** Canonical display colors for each BCV category. */
export const CATEGORY_COLORS: Record<BCVCategory, string> = {
  RSV: "#ef4444",
  PCV: "#f97316",
  SEV: "#eab308",
  ECV: "#8b5cf6",
  COV: "#06b6d4",
  CCV: "#64748b",
};

/** Human-readable labels for each BCV category. */
export const CATEGORY_LABELS: Record<BCVCategory, string> = {
  RSV: "Return Specification",
  PCV: "Parameter Contract",
  SEV: "Side Effect",
  ECV: "Exception Contract",
  COV: "Completeness Omission",
  CCV: "Complexity Contract",
};

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

/** Analysis record returned by the API. */
export interface Analysis {
  id: string;
  status: AnalysisStatus;
  filename: string | null;
  llmProvider: LLMProvider;
  totalFunctions: number;
  totalClaims: number;
  totalViolations: number;
  bcvRate: number;
  createdAt: string;
  completedAt: string | null;
}

/** Single behavioral claim: c_i = (τ_i, σ_i, ν_i, κ_i). */
export interface Claim {
  id: string;
  category: BCVCategory;
  subject: string;
  predicateObject: string;
  conditionality: string | null;
  sourceLine: number;
  rawText: string;
}

/** Single test execution result from the RV stage. */
export interface Violation {
  functionId: string;
  functionName: string;
  claim: Claim;
  testCode: string;
  outcome: TestOutcome;
  traceback: string | null;
  expected: string | null;
  actual: string | null;
}

/** Aggregated verification results for an analysis. */
export interface ViolationReport {
  analysisId: string;
  violations: Violation[];
  categoryBreakdown: Record<BCVCategory, number>;
  bcvRate: number;
  totalFunctions: number;
  totalClaims: number;
}

/** Per-category statistics for chart rendering. */
export interface CategoryStats {
  category: BCVCategory;
  count: number;
  percentage: number;
  color: string;
}
