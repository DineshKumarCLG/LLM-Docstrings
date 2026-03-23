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

/** Supported programming languages for analysis. (Requirements: 6.5) */
export type SupportedLanguage =
  | "python"
  | "javascript"
  | "typescript"
  | "java"
  | "go"
  | "rust";

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
  language: SupportedLanguage;
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

/** Batch analysis result — one batch = one ZIP upload. */
export interface BatchResult {
  batch_id: string;
  total: number;
  complete: number;
  failed: number;
  in_progress: number;
  analyses: Analysis[];
}

// ---------------------------------------------------------------------------
// Multi-language & folder upload types (Requirements: 6.5, 7.1)
// ---------------------------------------------------------------------------

/** A file with its relative path and detected language, used for folder uploads. */
export interface FileWithPath {
  file: File;
  relativePath: string;
  language: SupportedLanguage;
}

/** Payload for batch folder upload to the backend. */
export interface BatchUploadPayload {
  files: FileWithPath[];
  llm_provider: LLMProvider;
}

// ---------------------------------------------------------------------------
// Three-tab dashboard types (Requirements: 1.1, 6.1, 6.4, 8.4, 8.5, 10.1)
// ---------------------------------------------------------------------------

/** The three dashboard tab identifiers. */
export type DashboardTab = "documentation" | "verification" | "research";

/** A node in the documentation tree returned by the backend. */
export interface DocumentationNode {
  id: string;
  name: string;
  type: "module" | "class" | "function" | "method";
  docstring: string | null;
  signature: string | null;
  children: DocumentationNode[];
  lineno: number;
  endLineno: number | null;
}

/** Full documentation tree response from GET /api/analyses/:id/documentation. */
export interface DocumentationTree {
  analysisId: string;
  rootNodes: DocumentationNode[];
  generatedAt: string;
}

/** Per-function aggregated verification result. */
export interface FunctionVerificationResult {
  functionName: string;
  functionSignature: string;
  claims: Claim[];
  violations: Violation[];
  passCount: number;
  failCount: number;
  status: "all-pass" | "has-failures" | "no-claims";
}

/** Configuration for a single pipeline stage. */
export interface StageConfig {
  key: "bce" | "dts" | "rv";
  label: string;
  fullName: string;
  description: string;
  runningStatus: AnalysisStatus;
  completeStatus: AnalysisStatus;
}

/** Derived visual state for a pipeline stage. */
export interface StageState extends StageConfig {
  state: "pending" | "active" | "complete" | "failed";
}

/** Entry in the BCV taxonomy reference table. */
export interface BCVTaxonomyEntry {
  category: BCVCategory;
  fullName: string;
  description: string;
  hallucinationExample: string;
  correctBehavior: string;
}

/** PyBCV-420 benchmark statistics. */
export interface BenchmarkStats {
  totalInstances: number;
  categories: number;
  llmsTested: number;
  llmNames: string[];
  categoryDistribution: Record<BCVCategory, number>;
  detectionRates: Record<string, number>;
}

/** Group of claims extracted for a single function (used by Verification tab). */
export interface ClaimGroup {
  functionName: string;
  functionSignature: string;
  docstring: string | null;
  source: string;
  lineno: number;
  claims: Claim[];
}
