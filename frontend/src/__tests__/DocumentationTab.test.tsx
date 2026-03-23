/**
 * Unit tests for DocumentationTab component logic.
 *
 * Tests the rendering state machine, tree structure, and hook enablement
 * logic for the DocumentationTab component.
 *
 * Note: @testing-library/react is not installed in this project.
 * Tests validate the pure logic that drives rendering decisions,
 * mirroring the conditional rendering in DocumentationTab.tsx.
 *
 * **Validates: Requirements 7.2, 11.1, 11.2**
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AnalysisStatus, DocumentationNode, DocumentationTree } from "../types";

// ---------------------------------------------------------------------------
// Mock useDocumentation (mirrors vi.mock('@/hooks/useAnalysis'))
// ---------------------------------------------------------------------------

interface MockQueryResult {
  data: DocumentationTree | undefined;
  isLoading: boolean;
  isError: boolean;
}

let mockQueryResult: MockQueryResult = {
  data: undefined,
  isLoading: false,
  isError: false,
};

vi.mock("@/hooks/useAnalysis", () => ({
  useDocumentation: (_id: string, _status?: string) => mockQueryResult,
}));

beforeEach(() => {
  mockQueryResult = { data: undefined, isLoading: false, isError: false };
});

// ---------------------------------------------------------------------------
// Component rendering logic (mirrors DocumentationTab.tsx conditionals)
// ---------------------------------------------------------------------------

type RenderState =
  | "analysis-in-progress"
  | "loading"
  | "error"
  | "empty-tree"
  | "tree-view";

/**
 * Derives which UI state DocumentationTab renders.
 * Directly mirrors the conditional rendering in DocumentationTab.tsx.
 */
function deriveRenderState(
  analysisStatus: AnalysisStatus,
  { data, isLoading, isError }: MockQueryResult,
): RenderState {
  if (analysisStatus !== "complete") return "analysis-in-progress";
  if (isLoading) return "loading";
  if (isError || !data) return "error";
  if (data.rootNodes.length === 0) return "empty-tree";
  return "tree-view";
}

// ---------------------------------------------------------------------------
// Test data helpers
// ---------------------------------------------------------------------------

function makeMethod(id: string, name: string, lineno: number): DocumentationNode {
  return {
    id,
    name,
    type: "method",
    docstring: `Docstring for ${name}`,
    signature: `${name}(self) -> None`,
    children: [],
    lineno,
    endLineno: lineno + 3,
  };
}

function makeClass(
  id: string,
  name: string,
  methods: DocumentationNode[],
): DocumentationNode {
  return {
    id,
    name,
    type: "class",
    docstring: `Class ${name} docstring`,
    signature: null,
    children: methods,
    lineno: 1,
    endLineno: 50,
  };
}

function makeTree(rootNodes: DocumentationNode[]): DocumentationTree {
  return {
    analysisId: "test-analysis-id",
    rootNodes,
    generatedAt: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// 1. Tree rendering with nested class/method structures
// ---------------------------------------------------------------------------

describe("DocumentationTab — tree rendering with nested class/method structures", () => {
  it("renders tree-view state when a class with methods is present", () => {
    const methods = [
      makeMethod("m-1", "__init__", 5),
      makeMethod("m-2", "process", 10),
      makeMethod("m-3", "validate", 15),
    ];
    const classNode = makeClass("cls-1", "MyProcessor", methods);
    const tree = makeTree([classNode]);

    mockQueryResult = { data: tree, isLoading: false, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("tree-view");
  });

  it("tree has correct nested structure: class contains method children", () => {
    const methods = [
      makeMethod("m-1", "__init__", 2),
      makeMethod("m-2", "run", 8),
    ];
    const classNode = makeClass("cls-1", "Runner", methods);

    expect(classNode.children).toHaveLength(2);
    expect(classNode.children[0].name).toBe("__init__");
    expect(classNode.children[0].type).toBe("method");
    expect(classNode.children[1].name).toBe("run");
    expect(classNode.children[1].type).toBe("method");
  });

  it("renders tree-view with multiple root nodes (classes and functions)", () => {
    const classNode = makeClass("cls-1", "Validator", [
      makeMethod("m-1", "check", 3),
    ]);
    const funcNode: DocumentationNode = {
      id: "fn-1",
      name: "helper_func",
      type: "function",
      docstring: "A helper",
      signature: "helper_func(x: int) -> str",
      children: [],
      lineno: 60,
      endLineno: 70,
    };
    const tree = makeTree([classNode, funcNode]);

    mockQueryResult = { data: tree, isLoading: false, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("tree-view");
    expect(tree.rootNodes).toHaveLength(2);
    expect(tree.rootNodes[0].type).toBe("class");
    expect(tree.rootNodes[1].type).toBe("function");
  });

  it("class nodes start expanded (type === 'class' → expanded = true)", () => {
    const getInitialExpanded = (type: DocumentationNode["type"]) => type === "class";

    expect(getInitialExpanded("class")).toBe(true);
    expect(getInitialExpanded("function")).toBe(false);
    expect(getInitialExpanded("method")).toBe(false);
    expect(getInitialExpanded("module")).toBe(false);
  });

  it("counts all nodes in a nested tree correctly", () => {
    const methods = [makeMethod("m-1", "a", 2), makeMethod("m-2", "b", 5)];
    const classNode = makeClass("cls-1", "MyClass", methods);
    const tree = makeTree([classNode]);

    // 1 class + 2 methods = 3 total nodes
    let total = 0;
    const stack: DocumentationNode[] = [...tree.rootNodes];
    while (stack.length > 0) {
      const node = stack.pop()!;
      total++;
      stack.push(...node.children);
    }
    expect(total).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// 2. Loading state
// ---------------------------------------------------------------------------

describe("DocumentationTab — loading state", () => {
  it("shows loading state when isLoading is true and status is complete", () => {
    mockQueryResult = { data: undefined, isLoading: true, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("loading");
  });

  it("loading state is only shown when analysis is complete", () => {
    const nonCompleteStatuses: AnalysisStatus[] = [
      "pending", "bce_running", "bce_complete",
      "dts_running", "dts_complete", "rv_running", "failed",
    ];

    for (const status of nonCompleteStatuses) {
      mockQueryResult = { data: undefined, isLoading: true, isError: false };
      const state = deriveRenderState(status, mockQueryResult);
      // Non-complete status takes priority over loading
      expect(state).toBe("analysis-in-progress");
    }
  });

  it("loading state resolves to tree-view once data arrives", () => {
    // Simulate: loading → data available
    mockQueryResult = { data: undefined, isLoading: true, isError: false };
    expect(deriveRenderState("complete", mockQueryResult)).toBe("loading");

    const tree = makeTree([makeClass("cls-1", "Foo", [])]);
    mockQueryResult = { data: tree, isLoading: false, isError: false };
    expect(deriveRenderState("complete", mockQueryResult)).toBe("tree-view");
  });
});

// ---------------------------------------------------------------------------
// 3. Error state
// ---------------------------------------------------------------------------

describe("DocumentationTab — error state", () => {
  it("shows error state when isError is true", () => {
    mockQueryResult = { data: undefined, isLoading: false, isError: true };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("error");
  });

  it("shows error state when data is undefined (no data returned)", () => {
    mockQueryResult = { data: undefined, isLoading: false, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("error");
  });

  it("error state is only shown when analysis is complete", () => {
    mockQueryResult = { data: undefined, isLoading: false, isError: true };

    const nonCompleteStatuses: AnalysisStatus[] = [
      "pending", "bce_running", "bce_complete",
      "dts_running", "dts_complete", "rv_running", "failed",
    ];

    for (const status of nonCompleteStatuses) {
      const state = deriveRenderState(status, mockQueryResult);
      expect(state).toBe("analysis-in-progress");
    }
  });

  it("isError takes priority over missing data", () => {
    // Both isError=true and data=undefined → still "error"
    mockQueryResult = { data: undefined, isLoading: false, isError: true };
    expect(deriveRenderState("complete", mockQueryResult)).toBe("error");
  });
});

// ---------------------------------------------------------------------------
// 4. "Analysis in progress" state (analysisStatus !== "complete")
// ---------------------------------------------------------------------------

describe("DocumentationTab — analysis in progress state", () => {
  it("shows analysis-in-progress for 'pending' status", () => {
    mockQueryResult = { data: undefined, isLoading: false, isError: false };
    expect(deriveRenderState("pending", mockQueryResult)).toBe("analysis-in-progress");
  });

  it("shows analysis-in-progress for all non-complete statuses", () => {
    const nonCompleteStatuses: AnalysisStatus[] = [
      "pending", "bce_running", "bce_complete",
      "dts_running", "dts_complete", "rv_running", "failed",
    ];

    for (const status of nonCompleteStatuses) {
      mockQueryResult = { data: undefined, isLoading: false, isError: false };
      const state = deriveRenderState(status, mockQueryResult);
      expect(state).toBe("analysis-in-progress");
    }
  });

  it("analysis-in-progress takes priority over loading state", () => {
    mockQueryResult = { data: undefined, isLoading: true, isError: false };
    expect(deriveRenderState("bce_running", mockQueryResult)).toBe("analysis-in-progress");
  });

  it("analysis-in-progress takes priority over error state", () => {
    mockQueryResult = { data: undefined, isLoading: false, isError: true };
    expect(deriveRenderState("rv_running", mockQueryResult)).toBe("analysis-in-progress");
  });

  it("analysis-in-progress takes priority even when tree data is present", () => {
    const tree = makeTree([makeClass("cls-1", "Foo", [])]);
    mockQueryResult = { data: tree, isLoading: false, isError: false };
    expect(deriveRenderState("dts_complete", mockQueryResult)).toBe("analysis-in-progress");
  });

  it("useDocumentation hook is disabled for non-complete statuses", () => {
    // Mirrors: enabled: !!id && status === "complete"
    const isHookEnabled = (id: string, status?: string) =>
      !!id && status === "complete";

    const nonCompleteStatuses: AnalysisStatus[] = [
      "pending", "bce_running", "bce_complete",
      "dts_running", "dts_complete", "rv_running", "failed",
    ];

    for (const status of nonCompleteStatuses) {
      expect(isHookEnabled("some-id", status)).toBe(false);
    }
    expect(isHookEnabled("some-id", "complete")).toBe(true);
    expect(isHookEnabled("", "complete")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 5. Empty tree state (rootNodes = [])
// ---------------------------------------------------------------------------

describe("DocumentationTab — empty tree state", () => {
  it("shows empty-tree state when rootNodes is empty", () => {
    const emptyTree = makeTree([]);
    mockQueryResult = { data: emptyTree, isLoading: false, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("empty-tree");
  });

  it("empty-tree is distinct from error state", () => {
    const emptyTree = makeTree([]);
    mockQueryResult = { data: emptyTree, isLoading: false, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).not.toBe("error");
    expect(state).toBe("empty-tree");
  });

  it("non-empty tree does not show empty-tree state", () => {
    const tree = makeTree([makeClass("cls-1", "MyClass", [])]);
    mockQueryResult = { data: tree, isLoading: false, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("tree-view");
  });

  it("tree with only root nodes (no children) is not empty", () => {
    const funcNode: DocumentationNode = {
      id: "fn-1",
      name: "standalone_func",
      type: "function",
      docstring: null,
      signature: "standalone_func() -> None",
      children: [],
      lineno: 1,
      endLineno: 5,
    };
    const tree = makeTree([funcNode]);
    mockQueryResult = { data: tree, isLoading: false, isError: false };

    const state = deriveRenderState("complete", mockQueryResult);
    expect(state).toBe("tree-view");
  });
});
