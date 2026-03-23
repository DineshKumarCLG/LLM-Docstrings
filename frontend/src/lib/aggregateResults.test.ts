import { describe, it, expect } from "vitest";
import { aggregateFunctionResults } from "./aggregateResults";
import type { Violation, ClaimGroup, Claim } from "../types";

/** Helper to create a minimal Claim. */
function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    id: "claim-1",
    category: "RSV",
    subject: "fn",
    predicateObject: "returns number",
    conditionality: null,
    sourceLine: 1,
    rawText: "returns number",
    ...overrides,
  };
}

/** Helper to create a minimal ClaimGroup. */
function makeGroup(
  functionName: string,
  claims: Claim[] = [makeClaim()],
  functionSignature = `def ${functionName}()`,
): ClaimGroup {
  return {
    functionName,
    functionSignature,
    docstring: null,
    source: "",
    lineno: 1,
    claims,
  };
}

/** Helper to create a minimal Violation. */
function makeViolation(functionName: string, claim?: Claim): Violation {
  return {
    functionId: "fn-1",
    functionName,
    claim: claim ?? makeClaim(),
    testCode: "assert False",
    outcome: "fail",
    traceback: null,
    expected: null,
    actual: null,
  };
}

describe("aggregateFunctionResults", () => {
  it("returns empty array for empty inputs", () => {
    expect(aggregateFunctionResults([], [])).toEqual([]);
  });

  it("returns one result per unique function in claimGroups", () => {
    const groups = [makeGroup("foo"), makeGroup("bar"), makeGroup("baz")];
    const results = aggregateFunctionResults([], groups);
    expect(results).toHaveLength(3);
    const names = results.map((r) => r.functionName);
    expect(names).toContain("foo");
    expect(names).toContain("bar");
    expect(names).toContain("baz");
  });

  it("computes all-pass status when no violations exist", () => {
    const groups = [makeGroup("foo", [makeClaim(), makeClaim()])];
    const results = aggregateFunctionResults([], groups);
    expect(results[0]!.passCount).toBe(2);
    expect(results[0]!.failCount).toBe(0);
    expect(results[0]!.status).toBe("all-pass");
  });

  it("computes has-failures status when violations exist", () => {
    const claim = makeClaim();
    const groups = [makeGroup("foo", [claim, makeClaim({ id: "claim-2" })])];
    const violations = [makeViolation("foo", claim)];
    const results = aggregateFunctionResults(violations, groups);
    expect(results[0]!.passCount).toBe(1);
    expect(results[0]!.failCount).toBe(1);
    expect(results[0]!.status).toBe("has-failures");
  });

  it("computes no-claims status when function has zero claims", () => {
    const groups = [makeGroup("foo", [])];
    const results = aggregateFunctionResults([], groups);
    expect(results[0]!.passCount).toBe(0);
    expect(results[0]!.failCount).toBe(0);
    expect(results[0]!.status).toBe("no-claims");
  });

  it("passCount + failCount equals claims.length", () => {
    const claims = [makeClaim({ id: "c1" }), makeClaim({ id: "c2" }), makeClaim({ id: "c3" })];
    const groups = [makeGroup("foo", claims)];
    const violations = [makeViolation("foo"), makeViolation("foo")];
    const results = aggregateFunctionResults(violations, groups);
    expect(results[0]!.passCount + results[0]!.failCount).toBe(claims.length);
  });

  it("sorts results by failCount descending", () => {
    const groups = [
      makeGroup("clean", [makeClaim()]),
      makeGroup("broken", [makeClaim({ id: "c1" }), makeClaim({ id: "c2" })]),
      makeGroup("partial", [makeClaim({ id: "c3" }), makeClaim({ id: "c4" })]),
    ];
    const violations = [
      makeViolation("broken"),
      makeViolation("broken"),
      makeViolation("partial"),
    ];
    const results = aggregateFunctionResults(violations, groups);
    expect(results[0]!.functionName).toBe("broken");
    expect(results[0]!.failCount).toBe(2);
    expect(results[1]!.functionName).toBe("partial");
    expect(results[1]!.failCount).toBe(1);
    expect(results[2]!.functionName).toBe("clean");
    expect(results[2]!.failCount).toBe(0);
  });

  it("does not mutate input arrays", () => {
    const groups = [makeGroup("foo", [makeClaim()])];
    const violations = [makeViolation("foo")];
    const groupsCopy = JSON.stringify(groups);
    const violationsCopy = JSON.stringify(violations);

    aggregateFunctionResults(violations, groups);

    expect(JSON.stringify(groups)).toBe(groupsCopy);
    expect(JSON.stringify(violations)).toBe(violationsCopy);
  });

  it("ignores violations for functions not in claimGroups", () => {
    const groups = [makeGroup("foo", [makeClaim()])];
    const violations = [makeViolation("unknown_fn")];
    const results = aggregateFunctionResults(violations, groups);
    expect(results).toHaveLength(1);
    expect(results[0]!.functionName).toBe("foo");
    expect(results[0]!.failCount).toBe(0);
    expect(results[0]!.violations).toHaveLength(0);
  });

  it("caps failCount at claims.length when violations exceed claims", () => {
    const claims = [makeClaim()];
    const groups = [makeGroup("foo", claims)];
    // More violations than claims
    const violations = [makeViolation("foo"), makeViolation("foo"), makeViolation("foo")];
    const results = aggregateFunctionResults(violations, groups);
    // passCount + failCount must equal claims.length (Property 8)
    expect(results[0]!.passCount).toBe(0);
    expect(results[0]!.failCount).toBe(1);
    expect(results[0]!.passCount + results[0]!.failCount).toBe(claims.length);
    // All violations are still tracked for display
    expect(results[0]!.violations).toHaveLength(3);
    expect(results[0]!.status).toBe("has-failures");
  });
});
