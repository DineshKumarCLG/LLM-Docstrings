/**
 * Per-function result aggregation utilities.
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 5.1, 5.3
 */

import type { Violation, ClaimGroup, FunctionVerificationResult } from "../types";

/**
 * Aggregates violations and claim groups into per-function verification results.
 *
 * PRECONDITION:  violations and claimGroups reference the same analysis
 * POSTCONDITION: returns one result per unique function in claimGroups,
 *                with passCount + failCount === claims.length,
 *                sorted by failCount descending.
 *                Does not mutate input arrays.
 *
 * @param violations - Array of violations from the API
 * @param claimGroups - Array of claim groups from the API
 * @returns Sorted array of FunctionVerificationResult
 */
export function aggregateFunctionResults(
  violations: Violation[],
  claimGroups: ClaimGroup[],
): FunctionVerificationResult[] {
  const resultMap = new Map<string, FunctionVerificationResult>();

  // Step 1: Initialize from claim groups — assume all claims pass initially
  for (const group of claimGroups) {
    resultMap.set(group.functionName, {
      functionName: group.functionName,
      functionSignature: group.functionSignature,
      claims: group.claims,
      violations: [],
      passCount: group.claims.length,
      failCount: 0,
      status: group.claims.length > 0 ? "all-pass" : "no-claims",
    });
  }

  // Step 2: Overlay violations onto their respective functions
  // LOOP INVARIANT: all processed violations are assigned to their function
  for (const violation of violations) {
    const result = resultMap.get(violation.functionName);
    if (result) {
      result.violations.push(violation);
      // Only adjust counts when there are still passing claims to convert
      if (result.passCount > 0) {
        result.failCount += 1;
        result.passCount -= 1;
      }
      result.status = "has-failures";
    }
  }

  // Step 3: Sort by failCount descending (worst first)
  return Array.from(resultMap.values()).sort(
    (a, b) => b.failCount - a.failCount,
  );
}
