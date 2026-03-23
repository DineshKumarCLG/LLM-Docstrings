/**
 * Unit tests for DocumentationTab logic.
 *
 * Tests the state derivation, tree structure handling, and signature parsing
 * logic used by the DocumentationTab component — all as pure functions
 * without React rendering.
 *
 * **Validates: Requirements 7.2, 11.1, 11.2**
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import type { AnalysisStatus, DocumentationNode, DocumentationTree } from "../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

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

const NON_COMPLETE_STATUSES: AnalysisStatus[] = ALL_STATUSES.filter(
  (s) => s !== "complete",
);

// ---------------------------------------------------------------------------
// Pure logic extracted from DocumentationTab
// ---------------------------------------------------------------------------

/**
 * Determines which view state the DocumentationTab should display.
 * Mirrors the conditional rendering logic in DocumentationTab.tsx.
 */
type DocTabView =
  | "analysis-in-progress"
  | "loading"
  | "error"
  | "empty-tree"
  | "tree-view";

function deriveDocTabView(
  analysisStatus: AnalysisStatus,
  isLoading: boolean,
  isError: boolean,
  tree: DocumentationTree | undefined,
): DocTabView {
  const isComplete = analysisStatus === "complete";

  // Req 11.2: analysis not yet complete
  if (!isComplete) return "analysis-in-progress";

  // Loading state
  if (isLoading) return "loading";

  // Req 11.1: error or missing data
  if (isError || !tree) return "error";

  // Empty tree
  if (tree.rootNodes.length === 0) return "empty-tree";

  // Req 7.2: tree view
  return "tree-view";
}

/**
 * Parses a function signature into parts for syntax highlighting.
 * Mirrors the regex logic in SignatureHighlight component.
 */
function parseSignature(signature: string): {
  matched: boolean;
  name?: string;
  params?: string;
  returnType?: string;
  rest?: string;
} {
  const match = signature.match(/^([^(]+)(\([^)]*\))(.*)$/);
  if (!match) return { matched: false };

  const [, name, params, rest] = match;
  const arrowMatch = rest.match(/^(\s*->\s*)(.+)$/);

  return {
    matched: true,
    name,
    params,
    returnType: arrowMatch ? arrowMatch[2] : undefined,
    rest: arrowMatch ? undefined : rest,
  };
}

/**
 * Counts total nodes in a documentation tree (all levels).
 * Used to verify tree structure completeness (Req 7.2).
 */
function countNodes(nodes: DocumentationNode[]): number {
  let count = 0;
  for (const node of nodes) {
    count += 1;
    count += countNodes(node.children);
  }
  return count;
}

/**
 * Collects all node names from a tree (depth-first).
 */
function collectNodeNames(nodes: DocumentationNode[]): string[] {
  const names: string[] = [];
  for (const node of nodes) {
    names.push(node.name);
    names.push(...collectNodeNames(node.children));
  }
  return names;
}

/**
 * Determines the initial expanded state for a node.
 * Classes start expanded; functions/methods start collapsed.
 */
function getInitialExpanded(type: DocumentationNode["type"]): boolean {
  return type === "class";
}

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

const arbAnalysisStatus: fc.Arbitrary<AnalysisStatus> = fc.constantFrom(...ALL_STATUSES);

const arbNonCompleteStatus: fc.Arbitrary<AnalysisStatus> = fc.constantFrom(
  ...NON_COMPLETE_STATUSES,
);

const arbNodeType: fc.Arbitrary<DocumentationNode["type"]> = fc.constantFrom(
  "module" as const,
  "class" as const,
  "function" as const,
  "method" as const,
);

/** Arbitrary for a leaf DocumentationNode (no children). */
const arbLeafNode: fc.Arbitrary<DocumentationNode> = fc.record({
  id: fc.uuid(),
  name: fc.stringMatching(/^[a-z_][a-z0-9_]{0,19}$/),
  type: fc.constantFrom("function" as const, "method" as const),
  docstring: fc.option(fc.lorem({ maxCount: 5 }), { nil: null }),
  signature: fc.option(
    fc.tuple(
      fc.stringMatching(/^[a-z_][a-z0-9_]{0,9}$/),
      fc.stringMatching(/^[a-z_]{0,5}$/),
    ).map(([name, param]) => `${name}(${param}) -> None`),
    { nil: null },
  ),
  children: fc.constant([] as DocumentationNode[]),
  lineno: fc.integer({ min: 1, max: 500 }),
  endLineno: fc.option(fc.integer({ min: 1, max: 600 }), { nil: null }),
});

/** Arbitrary for a class node with method children. */
const arbClassNode: fc.Arbitrary<DocumentationNode> = fc
  .tuple(
    fc.uuid(),
    fc.stringMatching(/^[A-Z][a-zA-Z0-9]{0,14}$/),
    fc.option(fc.lorem({ maxCount: 3 }), { nil: null }),
    fc.array(arbLeafNode, { minLength: 0, maxLength: 5 }),
    fc.integer({ min: 1, max: 500 }),
    fc.option(fc.integer({ min: 1, max: 600 }), { nil: null }),
  )
  .map(([id, name, docstring, children, lineno, endLineno]) => ({
    id,
    name,
    type: "class" as const,
    docstring,
    signature: null,
    children,
    lineno,
    endLineno,
  }));

/** Arbitrary for a root-level node (function or class). */
const arbRootNode: fc.Arbitrary<DocumentationNode> = fc.oneof(arbLeafNode, arbClassNode);

/** Arbitrary for a non-empty DocumentationTree. */
const arbDocTree: fc.Arbitrary<DocumentationTree> = fc
  .tuple(
    fc.uuid(),
    fc.array(arbRootNode, { minLength: 1, maxLength: 8 }),
  )
  .map(([analysisId, rootNodes]) => ({
    analysisId,
    rootNodes,
    generatedAt: new Date().toISOString(),
  }));

/** Arbitrary for an empty DocumentationTree. */
const arbEmptyDocTree: fc.Arbitrary<DocumentationTree> = fc.uuid().map((id) => ({
  analysisId: id,
  rootNodes: [],
  generatedAt: new Date().toISOString(),
}));

// ---------------------------------------------------------------------------
// Tests: View state derivation (Req 11.1, 11.2)
// ---------------------------------------------------------------------------

describe("DocumentationTab — view state derivation", () => {
  /**
   * Req 11.2: Any non-complete status shows "analysis in progress".
   */
  it("shows 'analysis-in-progress' for any non-complete status", () => {
    fc.assert(
      fc.property(arbNonCompleteStatus, fc.boolean(), fc.boolean(), (status, isLoading, isError) => {
        const view = deriveDocTabView(status, isLoading, isError, undefined);
        expect(view).toBe("analysis-in-progress");
      }),
    );
  });

  /**
   * Req 11.2: "analysis in progress" takes priority over loading/error.
   */
  it("'analysis-in-progress' takes priority over loading and error states", () => {
    const tree: DocumentationTree = {
      analysisId: "test",
      rootNodes: [],
      generatedAt: new Date().toISOString(),
    };
    // Even with a tree available, non-complete status shows in-progress
    for (const status of NON_COMPLETE_STATUSES) {
      expect(deriveDocTabView(status, false, false, tree)).toBe("analysis-in-progress");
      expect(deriveDocTabView(status, true, false, tree)).toBe("analysis-in-progress");
      expect(deriveDocTabView(status, false, true, tree)).toBe("analysis-in-progress");
    }
  });

  /**
   * Loading state when analysis is complete but data is still fetching.
   */
  it("shows 'loading' when status is complete and isLoading is true", () => {
    expect(deriveDocTabView("complete", true, false, undefined)).toBe("loading");
  });

  /**
   * Req 11.1: Error state when fetch fails.
   */
  it("shows 'error' when status is complete and isError is true", () => {
    expect(deriveDocTabView("complete", false, true, undefined)).toBe("error");
  });

  /**
   * Req 11.1: Error state when tree data is undefined (no data returned).
   */
  it("shows 'error' when status is complete and tree is undefined", () => {
    expect(deriveDocTabView("complete", false, false, undefined)).toBe("error");
  });

  /**
   * Empty tree state.
   */
  it("shows 'empty-tree' when tree has no root nodes", () => {
    const emptyTree: DocumentationTree = {
      analysisId: "test",
      rootNodes: [],
      generatedAt: new Date().toISOString(),
    };
    expect(deriveDocTabView("complete", false, false, emptyTree)).toBe("empty-tree");
  });

  /**
   * Req 7.2: Tree view when data is available.
   */
  it("shows 'tree-view' when status is complete and tree has nodes", () => {
    fc.assert(
      fc.property(arbDocTree, (tree) => {
        const view = deriveDocTabView("complete", false, false, tree);
        expect(view).toBe("tree-view");
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: Tree structure (Req 7.2)
// ---------------------------------------------------------------------------

describe("DocumentationTab — tree structure", () => {
  /**
   * Req 7.2: countNodes correctly counts all nodes in nested structures.
   */
  it("countNodes counts all nodes including nested children", () => {
    fc.assert(
      fc.property(arbDocTree, (tree) => {
        const total = countNodes(tree.rootNodes);
        // Total must be at least the number of root nodes
        expect(total).toBeGreaterThanOrEqual(tree.rootNodes.length);

        // Total must equal root nodes + all their children recursively
        let expectedTotal = 0;
        const stack = [...tree.rootNodes];
        while (stack.length > 0) {
          const node = stack.pop()!;
          expectedTotal += 1;
          stack.push(...node.children);
        }
        expect(total).toBe(expectedTotal);
      }),
    );
  });

  /**
   * Req 7.2: collectNodeNames returns all names in depth-first order.
   */
  it("collectNodeNames returns every node name in the tree", () => {
    fc.assert(
      fc.property(arbDocTree, (tree) => {
        const names = collectNodeNames(tree.rootNodes);
        const total = countNodes(tree.rootNodes);
        expect(names.length).toBe(total);
      }),
    );
  });

  /**
   * Req 7.2: Class nodes with methods produce correct nested structure.
   */
  it("class nodes contain method children", () => {
    const classNode: DocumentationNode = {
      id: "cls-1",
      name: "MyClass",
      type: "class",
      docstring: "A test class",
      signature: null,
      children: [
        {
          id: "m-1",
          name: "__init__",
          type: "method",
          docstring: "Constructor",
          signature: "__init__(self, x: int) -> None",
          children: [],
          lineno: 2,
          endLineno: 5,
        },
        {
          id: "m-2",
          name: "process",
          type: "method",
          docstring: null,
          signature: "process(self) -> str",
          children: [],
          lineno: 7,
          endLineno: 10,
        },
      ],
      lineno: 1,
      endLineno: 10,
    };

    expect(countNodes([classNode])).toBe(3);
    expect(collectNodeNames([classNode])).toEqual(["MyClass", "__init__", "process"]);
  });
});

// ---------------------------------------------------------------------------
// Tests: Node expand/collapse logic
// ---------------------------------------------------------------------------

describe("DocumentationTab — node expand/collapse defaults", () => {
  /**
   * Classes start expanded; all other types start collapsed.
   */
  it("classes start expanded, functions/methods/modules start collapsed", () => {
    expect(getInitialExpanded("class")).toBe(true);
    expect(getInitialExpanded("function")).toBe(false);
    expect(getInitialExpanded("method")).toBe(false);
    expect(getInitialExpanded("module")).toBe(false);
  });

  /**
   * Property: only "class" type returns true for initial expanded state.
   */
  it("only class type is initially expanded (property)", () => {
    fc.assert(
      fc.property(arbNodeType, (type) => {
        const expanded = getInitialExpanded(type);
        if (type === "class") {
          expect(expanded).toBe(true);
        } else {
          expect(expanded).toBe(false);
        }
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: Signature parsing (Req 7.4)
// ---------------------------------------------------------------------------

describe("DocumentationTab — signature parsing", () => {
  it("parses a standard function signature with return type", () => {
    const result = parseSignature("my_func(x: int, y: str) -> bool");
    expect(result.matched).toBe(true);
    expect(result.name).toBe("my_func");
    expect(result.params).toBe("(x: int, y: str)");
    expect(result.returnType).toBe("bool");
  });

  it("parses a signature without return type", () => {
    const result = parseSignature("do_stuff(a, b)");
    expect(result.matched).toBe(true);
    expect(result.name).toBe("do_stuff");
    expect(result.params).toBe("(a, b)");
    expect(result.returnType).toBeUndefined();
    expect(result.rest).toBe("");
  });

  it("parses a signature with no parameters", () => {
    const result = parseSignature("get_value() -> int");
    expect(result.matched).toBe(true);
    expect(result.name).toBe("get_value");
    expect(result.params).toBe("()");
    expect(result.returnType).toBe("int");
  });

  it("returns matched=false for non-function signatures", () => {
    const result = parseSignature("just_a_name");
    expect(result.matched).toBe(false);
  });

  it("handles self parameter in method signatures", () => {
    const result = parseSignature("__init__(self, x: int) -> None");
    expect(result.matched).toBe(true);
    expect(result.name).toBe("__init__");
    expect(result.params).toBe("(self, x: int)");
    expect(result.returnType).toBe("None");
  });
});

// ---------------------------------------------------------------------------
// Tests: useDocumentation hook enablement logic
// ---------------------------------------------------------------------------

describe("DocumentationTab — useDocumentation enablement", () => {
  /**
   * The useDocumentation hook is only enabled when status === "complete".
   * This mirrors the `enabled: !!id && status === "complete"` logic.
   */
  function isHookEnabled(id: string, status?: string): boolean {
    return !!id && status === "complete";
  }

  it("hook is enabled only when id is non-empty and status is complete", () => {
    expect(isHookEnabled("abc-123", "complete")).toBe(true);
    expect(isHookEnabled("abc-123", "pending")).toBe(false);
    expect(isHookEnabled("abc-123", "bce_running")).toBe(false);
    expect(isHookEnabled("abc-123", undefined)).toBe(false);
    expect(isHookEnabled("", "complete")).toBe(false);
  });

  /**
   * Property: for any non-complete status, hook is disabled.
   */
  it("hook is disabled for any non-complete status (property)", () => {
    fc.assert(
      fc.property(arbNonCompleteStatus, fc.uuid(), (status, id) => {
        expect(isHookEnabled(id, status)).toBe(false);
      }),
    );
  });
});
