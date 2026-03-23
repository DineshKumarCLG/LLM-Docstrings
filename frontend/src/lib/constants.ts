/**
 * Static data constants for the three-tab dashboard.
 *
 * Requirements: 3.1, 9.3, 9.4, 10.1
 */

import type { BCVTaxonomyEntry, BenchmarkStats, StageConfig } from "../types";

// ---------------------------------------------------------------------------
// BCV Taxonomy — all 6 categories with full metadata (Requirement 3.1, 9.3)
// ---------------------------------------------------------------------------

export const BCV_TAXONOMY: BCVTaxonomyEntry[] = [
  {
    category: "RSV",
    fullName: "Return Specification Violation",
    description:
      "Docstring claims a return type/value that the function does not actually produce",
    hallucinationExample:
      "Docstring says 'returns a sorted list' but function returns unsorted",
    correctBehavior:
      "Function returns data matching the documented return specification",
  },
  {
    category: "PCV",
    fullName: "Parameter Contract Violation",
    description:
      "Docstring describes parameter constraints that the function does not enforce",
    hallucinationExample:
      "Docstring says 'x must be positive' but function accepts negative values",
    correctBehavior:
      "Function validates and enforces documented parameter constraints",
  },
  {
    category: "SEV",
    fullName: "Side Effect Violation",
    description:
      "Docstring claims no side effects but function mutates input or global state",
    hallucinationExample:
      "Docstring says 'does not modify input' but function sorts list in-place",
    correctBehavior: "Function's side effects match what is documented",
  },
  {
    category: "ECV",
    fullName: "Exception Contract Violation",
    description:
      "Docstring documents exceptions that are not raised, or raises undocumented ones",
    hallucinationExample:
      "Docstring says 'raises ValueError for empty input' but function returns None",
    correctBehavior:
      "Function raises exactly the documented exceptions under documented conditions",
  },
  {
    category: "COV",
    fullName: "Completeness Omission Violation",
    description:
      "Docstring omits significant behavior branches or edge cases",
    hallucinationExample:
      "Docstring doesn't mention that function returns None for empty input",
    correctBehavior: "Docstring covers all significant behavior paths",
  },
  {
    category: "CCV",
    fullName: "Complexity Contract Violation",
    description:
      "Docstring claims a time/space complexity that the implementation does not achieve",
    hallucinationExample:
      "Docstring says 'O(n log n)' but implementation is O(n²)",
    correctBehavior:
      "Implementation complexity matches documented complexity bounds",
  },
];

// ---------------------------------------------------------------------------
// PyBCV-420 Benchmark Statistics (Requirement 9.4)
// ---------------------------------------------------------------------------

export const PYBCV_420_STATS: BenchmarkStats = {
  totalInstances: 420,
  categories: 6,
  llmsTested: 3,
  llmNames: ["GPT-4.1 Mini", "Claude Sonnet 4", "Gemini 3 Flash"],
  categoryDistribution: {
    RSV: 70,
    PCV: 70,
    SEV: 70,
    ECV: 70,
    COV: 70,
    CCV: 70,
  },
  detectionRates: {
    "GPT-4.1 Mini": 0.0,
    "Claude Sonnet 4": 0.0,
    "Gemini 3 Flash": 0.0,
  },
};

// ---------------------------------------------------------------------------
// Pipeline Stage Configuration (Requirement 10.1)
// ---------------------------------------------------------------------------

export const PIPELINE_STAGES: StageConfig[] = [
  {
    key: "bce",
    label: "BCE",
    fullName: "Behavioral Claim Extractor",
    description:
      "Extracts behavioral claims from docstrings and source code",
    runningStatus: "bce_running",
    completeStatus: "bce_complete",
  },
  {
    key: "dts",
    label: "DTS",
    fullName: "Differential Test Synthesizer",
    description:
      "Synthesizes property-based tests from extracted claims",
    runningStatus: "dts_running",
    completeStatus: "dts_complete",
  },
  {
    key: "rv",
    label: "RV",
    fullName: "Runtime Verifier",
    description:
      "Executes synthesized tests and reports violations",
    runningStatus: "rv_running",
    completeStatus: "complete",
  },
];
