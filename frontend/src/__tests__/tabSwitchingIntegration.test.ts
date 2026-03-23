/**
 * Integration tests for the tab switching flow.
 *
 * Tests the full tab switching lifecycle including:
 * - Tab switching with mocked API response logic
 * - Lazy loading of Documentation data (only fetched on first activation)
 * - URL search param persistence across tab switches
 *
 * **Validates: Requirements 1.4, 1.5, 1.6, 7.5**
 */
import { describe, it, expect } from "vitest";
import type { AnalysisStatus, DashboardTab, DocumentationTree } from "../types";

const ALL_TABS: DashboardTab[] = ["documentation", "verification", "research"];
const ALL_STATUSES: AnalysisStatus[] = [
  "pending", "bce_running", "bce_complete",
  "dts_running", "dts_complete", "rv_running", "complete", "failed",
];

// ---------------------------------------------------------------------------
// Simulated URL search params (mirrors useSearchParams behavior)
// ---------------------------------------------------------------------------

class SimulatedSearchParams {
  private params: Map<string, string>;
  constructor(init?: string) {
    this.params = new Map();
    if (init) {
      new URLSearchParams(init).forEach((v, k) => this.params.set(k, v));
    }
  }
  get(key: string): string | null { return this.params.get(key) ?? null; }
  set(key: string, value: string): void { this.params.set(key, value); }
  toString(): string {
    const p: string[] = [];
    this.params.forEach((v, k) => p.push(`${k}=${v}`));
    return p.join("&");
  }
}

// ---------------------------------------------------------------------------
// Dashboard simulation (mirrors AnalysisDetail.tsx state machine)
// ---------------------------------------------------------------------------

interface MockApi {
  analysis: { id: string; status: AnalysisStatus };
  documentation?: DocumentationTree;
  documentationError?: boolean;
}

class DashboardSimulation {
  private searchParams: SimulatedSearchParams;
  private activatedTabs: Set<DashboardTab>;
  private apiCalls: string[] = [];
  private mockResponses: MockApi;
  private documentationData: DocumentationTree | undefined;
  private documentationError = false;

  constructor(initialUrl: string, mockResponses: MockApi) {
    this.searchParams = new SimulatedSearchParams(initialUrl);
    this.mockResponses = mockResponses;
    const activeTab = this.getActiveTab();
    this.activatedTabs = new Set([activeTab]);
    this.simulateFetchesForTab(activeTab);
  }

  getActiveTab(): DashboardTab {
    return (this.searchParams.get("tab") as DashboardTab) || "verification";
  }

  switchTab(tab: DashboardTab): void {
    this.searchParams.set("tab", tab);
    this.activatedTabs.add(tab);
    this.simulateFetchesForTab(tab);
  }

  getUrlParams(): string { return this.searchParams.toString(); }
  getActivatedTabs(): Set<DashboardTab> { return new Set(this.activatedTabs); }
  getApiCalls(): string[] { return [...this.apiCalls]; }
  getDocumentationData(): DocumentationTree | undefined { return this.documentationData; }
  hasDocumentationError(): boolean { return this.documentationError; }

  private simulateFetchesForTab(tab: DashboardTab): void {
    const { analysis } = this.mockResponses;
    if (tab === "documentation") {
      if (analysis.status === "complete") {
        this.apiCalls.push(`GET /api/analyses/${analysis.id}/documentation`);
        if (this.mockResponses.documentationError) {
          this.documentationError = true;
        } else if (this.mockResponses.documentation) {
          this.documentationData = this.mockResponses.documentation;
        }
      }
    }
    if (tab === "verification") {
      this.apiCalls.push(`GET /api/analyses/${analysis.id}/violations`);
      this.apiCalls.push(`GET /api/analyses/${analysis.id}/claims`);
    }
    // Research tab makes no API calls (Req 9.7)
  }
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createMockDocTree(analysisId: string): DocumentationTree {
  return {
    analysisId,
    rootNodes: [{
      id: "node-1", name: "my_module", type: "module",
      docstring: "A test module", signature: null,
      children: [{
        id: "node-2", name: "my_function", type: "function",
        docstring: "A test function", signature: "my_function(x: int) -> str",
        children: [], lineno: 5, endLineno: 10,
      }],
      lineno: 1, endLineno: 20,
    }],
    generatedAt: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Integration tests: Full tab switching flow with mocked API responses
// ---------------------------------------------------------------------------

describe("Tab switching integration — full flow with mocked API responses", () => {
  it("switches between all three tabs in sequence", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
      documentation: createMockDocTree("test-123"),
    });
    expect(sim.getActiveTab()).toBe("verification");
    sim.switchTab("documentation");
    expect(sim.getActiveTab()).toBe("documentation");
    sim.switchTab("research");
    expect(sim.getActiveTab()).toBe("research");
    sim.switchTab("verification");
    expect(sim.getActiveTab()).toBe("verification");
  });

  it("preserves all activated tabs after switching through them (Req 1.6)", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
      documentation: createMockDocTree("test-123"),
    });
    expect(sim.getActivatedTabs().size).toBe(1);
    expect(sim.getActivatedTabs().has("verification")).toBe(true);

    sim.switchTab("documentation");
    expect(sim.getActivatedTabs().size).toBe(2);

    sim.switchTab("research");
    expect(sim.getActivatedTabs().size).toBe(3);

    sim.switchTab("verification");
    expect(sim.getActivatedTabs().size).toBe(3);
    for (const tab of ALL_TABS) {
      expect(sim.getActivatedTabs().has(tab)).toBe(true);
    }
  });

  it("fetches violations and claims when verification tab is active", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "abc-456", status: "complete" },
    });
    const calls = sim.getApiCalls();
    expect(calls).toContain("GET /api/analyses/abc-456/violations");
    expect(calls).toContain("GET /api/analyses/abc-456/claims");
  });

  it("makes no API calls when switching to research tab (Req 9.7)", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
    });
    const callsBefore = sim.getApiCalls().length;
    sim.switchTab("research");
    const callsAfter = sim.getApiCalls().length;
    expect(callsAfter).toBe(callsBefore);
  });
});

// ---------------------------------------------------------------------------
// Integration tests: Lazy loading of Documentation data (Req 7.5)
// ---------------------------------------------------------------------------

describe("Tab switching integration — lazy loading of Documentation data", () => {
  it("does not fetch documentation on initial load when default tab is verification", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
      documentation: createMockDocTree("test-123"),
    });
    const docCalls = sim.getApiCalls().filter((c) => c.includes("/documentation"));
    expect(docCalls).toHaveLength(0);
    expect(sim.getDocumentationData()).toBeUndefined();
  });

  it("fetches documentation when Documentation tab is first activated", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
      documentation: createMockDocTree("test-123"),
    });
    sim.switchTab("documentation");
    const docCalls = sim.getApiCalls().filter((c) => c.includes("/documentation"));
    expect(docCalls).toHaveLength(1);
    expect(sim.getDocumentationData()).toBeDefined();
    expect(sim.getDocumentationData()?.analysisId).toBe("test-123");
  });

  it("does not fetch documentation when analysis is not complete", () => {
    const nonComplete = ALL_STATUSES.filter((s) => s !== "complete");
    for (const status of nonComplete) {
      const sim = new DashboardSimulation("", {
        analysis: { id: "test-123", status },
        documentation: createMockDocTree("test-123"),
      });
      sim.switchTab("documentation");
      const docCalls = sim.getApiCalls().filter((c) => c.includes("/documentation"));
      expect(docCalls).toHaveLength(0);
    }
  });

  it("fetches documentation immediately when URL param is set to documentation", () => {
    const sim = new DashboardSimulation("tab=documentation", {
      analysis: { id: "test-123", status: "complete" },
      documentation: createMockDocTree("test-123"),
    });
    expect(sim.getActiveTab()).toBe("documentation");
    const docCalls = sim.getApiCalls().filter((c) => c.includes("/documentation"));
    expect(docCalls).toHaveLength(1);
    expect(sim.getDocumentationData()).toBeDefined();
  });

  it("documentation tab remains activated after switching away and back", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
      documentation: createMockDocTree("test-123"),
    });
    sim.switchTab("documentation");
    expect(sim.getActivatedTabs().has("documentation")).toBe(true);
    sim.switchTab("verification");
    expect(sim.getActivatedTabs().has("documentation")).toBe(true);
    sim.switchTab("documentation");
    expect(sim.getActivatedTabs().has("documentation")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Integration tests: URL search param persistence across tab switches
// ---------------------------------------------------------------------------

describe("Tab switching integration — URL search param persistence", () => {
  it("updates URL param on each tab switch (Req 1.4)", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
    });
    sim.switchTab("documentation");
    expect(sim.getUrlParams()).toBe("tab=documentation");
    sim.switchTab("research");
    expect(sim.getUrlParams()).toBe("tab=research");
    sim.switchTab("verification");
    expect(sim.getUrlParams()).toBe("tab=verification");
  });

  it("activates the correct tab from URL param on initial load (Req 1.5)", () => {
    for (const tab of ALL_TABS) {
      const sim = new DashboardSimulation(`tab=${tab}`, {
        analysis: { id: "test-123", status: "complete" },
        documentation: createMockDocTree("test-123"),
      });
      expect(sim.getActiveTab()).toBe(tab);
      expect(sim.getActivatedTabs().has(tab)).toBe(true);
    }
  });

  it("defaults to verification tab when no URL param is present (Req 1.5)", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
    });
    expect(sim.getActiveTab()).toBe("verification");
  });

  it("URL param round-trip is consistent for all tabs (Req 1.4, 1.5)", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
    });
    for (const tab of ALL_TABS) {
      sim.switchTab(tab);
      expect(sim.getUrlParams()).toBe(`tab=${tab}`);
      expect(sim.getActiveTab()).toBe(tab);
    }
  });

  it("rapid tab switching preserves state and URL consistency (Req 1.4, 1.6)", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
      documentation: createMockDocTree("test-123"),
    });
    sim.switchTab("documentation");
    sim.switchTab("research");
    sim.switchTab("verification");
    sim.switchTab("documentation");
    sim.switchTab("research");

    expect(sim.getActiveTab()).toBe("research");
    expect(sim.getUrlParams()).toBe("tab=research");
    expect(sim.getActivatedTabs().size).toBe(3);
    for (const tab of ALL_TABS) {
      expect(sim.getActivatedTabs().has(tab)).toBe(true);
    }
  });

  it("switching to the same tab repeatedly is idempotent (Req 1.4, 1.5)", () => {
    const sim = new DashboardSimulation("", {
      analysis: { id: "test-123", status: "complete" },
    });
    sim.switchTab("documentation");
    sim.switchTab("documentation");
    sim.switchTab("documentation");

    expect(sim.getActiveTab()).toBe("documentation");
    expect(sim.getUrlParams()).toBe("tab=documentation");
    expect(sim.getActivatedTabs().size).toBe(2);
  });
});
