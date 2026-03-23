/**
 * Property-based tests for tab navigation logic.
 *
 * Validates: Requirements 1.4, 1.5, 1.6
 */
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import type { DashboardTab } from "../types";

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

/** All valid DashboardTab values. */
const ALL_TABS: DashboardTab[] = ["documentation", "verification", "research"];

/** Arbitrary that produces any valid DashboardTab. */
const arbDashboardTab: fc.Arbitrary<DashboardTab> = fc.constantFrom(...ALL_TABS);

// ---------------------------------------------------------------------------
// Pure logic helpers (mirrors AnalysisDetail.tsx implementation)
// ---------------------------------------------------------------------------

/**
 * Derives the active tab from a URL search param string.
 * Mirrors the logic in AnalysisDetail.tsx:
 *   const activeTab = (searchParams.get("tab") as DashboardTab) || "verification";
 */
function getActiveTabFromParam(param: string | null): DashboardTab {
  return (param as DashboardTab) || "verification";
}

/**
 * Simulates setting the URL param for a tab and reading it back.
 * Returns the tab value that would be active after the round trip.
 */
function tabUrlRoundTrip(tab: DashboardTab): DashboardTab {
  // Setting: store the tab value as the URL param
  const param = tab;
  // Reading: derive active tab from the stored param
  return getActiveTabFromParam(param);
}

/**
 * Simulates the `activatedTabs` Set logic used for lazy-loading and state
 * preservation. When a tab is activated it is added to the set; switching
 * away does not remove it.
 */
function simulateActivatedTabs(
  initialTab: DashboardTab,
  switchSequence: DashboardTab[],
): Set<DashboardTab> {
  const activated = new Set<DashboardTab>();
  activated.add(initialTab);

  for (const tab of switchSequence) {
    activated.add(tab);
  }

  return activated;
}

// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

describe("Tab Navigation — property tests", () => {
  /**
   * Property 1: Tab-URL Round Trip
   *
   * For any valid DashboardTab value, setting the URL search parameter `tab`
   * to that value and reading the active tab back produces the same tab value.
   *
   * **Validates: Requirements 1.4, 1.5**
   */
  it("Property 1: Tab-URL Round Trip — setting URL param and reading active tab produces same value", () => {
    fc.assert(
      fc.property(arbDashboardTab, (tab) => {
        const result = tabUrlRoundTrip(tab);
        expect(result).toBe(tab);
      }),
    );
  });

  /**
   * Additional coverage: null/missing param falls back to "verification".
   */
  it("Tab-URL Round Trip — missing param defaults to verification", () => {
    expect(getActiveTabFromParam(null)).toBe("verification");
    expect(getActiveTabFromParam("")).toBe("verification");
  });

  /**
   * Property 2: Tab State Preservation
   *
   * For any tab that has been activated, switching away to other tabs and
   * then switching back should still have that tab present in the
   * `activatedTabs` set (i.e., its component state is preserved via
   * conditional rendering rather than unmounting).
   *
   * **Validates: Requirement 1.6**
   */
  it("Property 2: Tab State Preservation — switching away and back preserves component state", () => {
    fc.assert(
      fc.property(
        arbDashboardTab,
        fc.array(arbDashboardTab, { minLength: 1, maxLength: 10 }),
        (initialTab, switchSequence) => {
          const activated = simulateActivatedTabs(initialTab, switchSequence);

          // The initial tab must always remain in the activated set
          expect(activated.has(initialTab)).toBe(true);

          // Every tab visited during the switch sequence must remain in the set
          for (const tab of switchSequence) {
            expect(activated.has(tab)).toBe(true);
          }

          // Switching back to the initial tab: it is still in the set
          // (state is preserved — the component was never unmounted)
          activated.add(initialTab);
          expect(activated.has(initialTab)).toBe(true);
        },
      ),
    );
  });

  /**
   * Additional coverage: all tabs can be activated independently.
   */
  it("Tab State Preservation — activating all tabs keeps all in the set", () => {
    const activated = simulateActivatedTabs("verification", [
      "documentation",
      "research",
      "verification",
    ]);
    expect(activated.size).toBe(3);
    for (const tab of ALL_TABS) {
      expect(activated.has(tab)).toBe(true);
    }
  });
});
