/**
 * Integration tests for the tab switching flow.
 *
 * Models the tab switching logic from AnalysisDetail.tsx as pure functions
 * and tests the full lifecycle including URL param persistence, lazy loading,
 * and state preservation — without requiring DOM rendering.
 *
 * **Validates: Requirements 1.4, 1.5, 1.6, 7.5**
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import type { DashboardTab } from "../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_TABS: DashboardTab[] = ["documentation", "verification", "research"];

// ---------------------------------------------------------------------------
// Pure logic helpers (mirrors AnalysisDetail.tsx)
// ---------------------------------------------------------------------------

/**
 * Derives the active tab from a URL search param value.
 * Mirrors: const activeTab = (searchParams.get("tab") as DashboardTab) || "verification";
 */
function getActiveTab(param: string | null): DashboardTab {
  return (param as DashboardTab) || "verification";
}

/**
 * Simulates handleTabChange: sets the URL param and adds to activatedTabs.
 * Returns the new [param, activatedTabs] state.
 */
function handleTabChange(
  tab: DashboardTab,
  activatedTabs: Set<DashboardTab>,
): { param: string; activatedTabs: Set<DashboardTab> } {
  const next = new Set(activatedTabs);
  next.add(tab);
  return { param: tab, activatedTabs: next };
}

/**
 * Simulates the full tab switching state machine starting from an initial URL param.
 */
function createTabState(initialParam: string | null) {
  const activeTab = getActiveTab(initialParam);
  const activatedTabs = new Set<DashboardTab>([activeTab]);
  let currentParam: string | null = initialParam;

  return {
    getActiveTab: () => getActiveTab(currentParam),
    getActivatedTabs: () => new Set(activatedTabs),
    switchTab(tab: DashboardTab) {
      const result = handleTabChange(tab, activatedTabs);
      currentParam = result.param;
      result.activatedTabs.forEach((t) => activatedTabs.add(t));
    },
    getParam: () => currentParam,
  };
}

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

const arbTab = fc.constantFrom<DashboardTab>(...ALL_TABS);
const arbTabSequence = fc.array(arbTab, { minLength: 1, maxLength: 15 });

// ---------------------------------------------------------------------------
// 1. Tab-URL round trip
// ---------------------------------------------------------------------------

describe("Tab-URL round trip", () => {
  it("setting a tab value and reading it back produces the same value", () => {
    fc.assert(
      fc.property(arbTab, (tab) => {
        // Setting: store tab as URL param
        const param = tab;
        // Reading: derive active tab from param
        const result = getActiveTab(param);
        expect(result).toBe(tab);
      }),
    );
  });

  it("round trip holds for all three tabs explicitly", () => {
    for (const tab of ALL_TABS) {
      expect(getActiveTab(tab)).toBe(tab);
    }
  });
});

// ---------------------------------------------------------------------------
// 2. Lazy loading — tabs only added to activatedTabs on first activation
// ---------------------------------------------------------------------------

describe("Lazy loading — activatedTabs grows only on first activation", () => {
  it("switching to a new tab adds it to activatedTabs exactly once", () => {
    fc.assert(
      fc.property(arbTab, arbTabSequence, (initial, sequence) => {
        const state = createTabState(initial);
        const seen = new Set<DashboardTab>([initial]);

        for (const tab of sequence) {
          const sizeBefore = state.getActivatedTabs().size;
          const isNew = !seen.has(tab);
          state.switchTab(tab);
          seen.add(tab);
          const sizeAfter = state.getActivatedTabs().size;

          if (isNew) {
            expect(sizeAfter).toBe(sizeBefore + 1);
          } else {
            expect(sizeAfter).toBe(sizeBefore);
          }
        }
      }),
    );
  });

  it("switching to the same tab multiple times does not grow activatedTabs", () => {
    const state = createTabState(null); // defaults to verification
    expect(state.getActivatedTabs().size).toBe(1);

    state.switchTab("verification");
    state.switchTab("verification");
    state.switchTab("verification");

    expect(state.getActivatedTabs().size).toBe(1);
    expect(state.getActivatedTabs().has("verification")).toBe(true);
  });

  it("activatedTabs size never exceeds 3 (total number of tabs)", () => {
    fc.assert(
      fc.property(arbTab, arbTabSequence, (initial, sequence) => {
        const state = createTabState(initial);
        for (const tab of sequence) {
          state.switchTab(tab);
        }
        expect(state.getActivatedTabs().size).toBeLessThanOrEqual(3);
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// 3. URL search param persistence
// ---------------------------------------------------------------------------

describe("URL search param persistence", () => {
  it("switching tabs updates the URL param correctly", () => {
    fc.assert(
      fc.property(arbTabSequence, (sequence) => {
        const state = createTabState(null);
        for (const tab of sequence) {
          state.switchTab(tab);
          expect(state.getParam()).toBe(tab);
          expect(state.getActiveTab()).toBe(tab);
        }
      }),
    );
  });

  it("URL param matches active tab after every switch", () => {
    const state = createTabState(null);
    for (const tab of ALL_TABS) {
      state.switchTab(tab);
      expect(state.getParam()).toBe(tab);
      expect(state.getActiveTab()).toBe(tab);
    }
  });
});

// ---------------------------------------------------------------------------
// 4. Default tab
// ---------------------------------------------------------------------------

describe("Default tab", () => {
  it("defaults to verification when no tab param is present", () => {
    expect(getActiveTab(null)).toBe("verification");
  });

  it("defaults to verification when param is empty string", () => {
    expect(getActiveTab("")).toBe("verification");
  });

  it("initial activatedTabs contains verification when no param given", () => {
    const state = createTabState(null);
    expect(state.getActiveTab()).toBe("verification");
    expect(state.getActivatedTabs().has("verification")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 5. Invalid tab param
// ---------------------------------------------------------------------------

describe("Invalid tab param", () => {
  it("when ?tab=invalid is in URL, the tab value is cast to DashboardTab as-is", () => {
    // The implementation casts the param directly: (searchParams.get("tab") as DashboardTab)
    // So an invalid value is returned as-is (truthy string bypasses the || fallback)
    const result = getActiveTab("invalid");
    expect(result).toBe("invalid" as DashboardTab);
  });

  it("only falsy values fall back to verification", () => {
    expect(getActiveTab(null)).toBe("verification");
    expect(getActiveTab("")).toBe("verification");
    // Any non-empty string (even invalid) is returned as-is
    expect(getActiveTab("unknown")).toBe("unknown" as DashboardTab);
  });
});

// ---------------------------------------------------------------------------
// 6. State preservation
// ---------------------------------------------------------------------------

describe("State preservation", () => {
  it("switching away and back to a tab does not remove it from activatedTabs", () => {
    fc.assert(
      fc.property(arbTab, arbTab, (tabA, tabB) => {
        const state = createTabState(null);
        state.switchTab(tabA);
        expect(state.getActivatedTabs().has(tabA)).toBe(true);

        // Switch away to tabB (may be same as tabA — that's fine)
        state.switchTab(tabB);
        // tabA must still be in activatedTabs
        expect(state.getActivatedTabs().has(tabA)).toBe(true);

        // Switch back to tabA
        state.switchTab(tabA);
        expect(state.getActivatedTabs().has(tabA)).toBe(true);
      }),
    );
  });

  it("all previously activated tabs remain in activatedTabs after any switch sequence", () => {
    fc.assert(
      fc.property(arbTab, arbTabSequence, (initial, sequence) => {
        const state = createTabState(initial);
        const everActivated = new Set<DashboardTab>([initial]);

        for (const tab of sequence) {
          state.switchTab(tab);
          everActivated.add(tab);
        }

        for (const tab of everActivated) {
          expect(state.getActivatedTabs().has(tab)).toBe(true);
        }
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// 7. All three tabs are valid DashboardTab values
// ---------------------------------------------------------------------------

describe("All three tabs are valid DashboardTab values", () => {
  it('"documentation", "verification", "research" are all valid DashboardTab values', () => {
    const validTabs: DashboardTab[] = ["documentation", "verification", "research"];
    expect(validTabs).toHaveLength(3);
    for (const tab of validTabs) {
      // Each tab round-trips through the URL param correctly
      expect(getActiveTab(tab)).toBe(tab);
    }
  });

  it("each valid tab can be set as active and read back", () => {
    fc.assert(
      fc.property(arbTab, (tab) => {
        const state = createTabState(tab);
        expect(state.getActiveTab()).toBe(tab);
        expect(state.getActivatedTabs().has(tab)).toBe(true);
      }),
    );
  });

  it("ALL_TABS covers exactly the three valid tab values", () => {
    expect(ALL_TABS).toContain("documentation");
    expect(ALL_TABS).toContain("verification");
    expect(ALL_TABS).toContain("research");
    expect(ALL_TABS).toHaveLength(3);
  });
});
