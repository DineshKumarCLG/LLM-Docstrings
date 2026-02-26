/**
 * Code viewer with inline violation annotations.
 *
 * Displays Python source with line numbers, highlights violated lines,
 * shows gutter markers, and provides hover tooltips with claim + violation details.
 *
 * Requirements: 8.7
 */

import { useState, useMemo } from "react";
import {
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  type Violation,
} from "@/types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CodeViewerProps {
  sourceCode: string;
  violations: Violation[];
}

// ---------------------------------------------------------------------------
// Build a lookup: line number → violations on that line
// ---------------------------------------------------------------------------

function buildLineViolationMap(violations: Violation[]) {
  const map = new Map<number, Violation[]>();
  for (const v of violations) {
    if (v.claim.sourceLine > 0) {
      const line = v.claim.sourceLine;
      const list = map.get(line) ?? [];
      list.push(v);
      map.set(line, list);
    }
  }
  return map;
}

// ---------------------------------------------------------------------------
// Tooltip component (positioned absolutely near the hovered line)
// ---------------------------------------------------------------------------

function ViolationTooltip({ violations }: { violations: Violation[] }) {
  return (
    <div className="absolute left-full top-0 z-50 ml-2 w-80 rounded-lg border bg-popover p-3 shadow-lg text-popover-foreground">
      <p className="mb-2 text-xs font-semibold text-muted-foreground">
        {violations.length} violation{violations.length !== 1 ? "s" : ""} on
        this line
      </p>
      <div className="space-y-2">
        {violations.map((v, i) => (
          <div key={i} className="rounded-md border p-2 text-xs">
            <div className="mb-1 flex items-center gap-2">
              <span
                className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold text-white"
                style={{
                  backgroundColor: CATEGORY_COLORS[v.claim.category],
                }}
              >
                {v.claim.category}
              </span>
              <span className="font-medium">
                {CATEGORY_LABELS[v.claim.category]}
              </span>
            </div>
            <p className="text-muted-foreground">{v.claim.rawText}</p>
            {v.expected && (
              <p className="mt-1">
                <span className="font-medium">Expected:</span>{" "}
                <span className="font-mono">{v.expected}</span>
              </p>
            )}
            {v.actual && (
              <p>
                <span className="font-medium">Actual:</span>{" "}
                <span className="font-mono">{v.actual}</span>
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CodeViewer({ sourceCode, violations }: CodeViewerProps) {
  const [hoveredLine, setHoveredLine] = useState<number | null>(null);

  const lines = useMemo(() => sourceCode.split("\n"), [sourceCode]);
  const lineViolationMap = useMemo(
    () => buildLineViolationMap(violations),
    [violations],
  );

  const gutterWidth = String(lines.length).length;

  return (
    <div className="overflow-x-auto rounded-lg border bg-card">
      <pre className="text-sm leading-6">
        <code>
          {lines.map((line, idx) => {
            const lineNum = idx + 1;
            const lineViolations = lineViolationMap.get(lineNum);

            return (
              <div
                key={lineNum}
                className="relative"
                onMouseEnter={() => lineViolations && setHoveredLine(lineNum)}
                onMouseLeave={() => setHoveredLine(null)}
              >
                <div
                  className={
                    lineViolations
                      ? "flex bg-red-500/10 hover:bg-red-500/20"
                      : "flex hover:bg-muted/40"
                  }
                >
                  {/* Gutter: line number + marker */}
                  <span className="sticky left-0 flex shrink-0 select-none items-center gap-1 border-r bg-muted/30 px-2 text-right text-xs text-muted-foreground">
                    {(() => {
                      const first = lineViolations?.[0];
                      if (!first) return null;
                      return (
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{
                            backgroundColor:
                              CATEGORY_COLORS[first.claim.category],
                          }}
                          aria-label={`Violation: ${first.claim.category}`}
                        />
                      );
                    })()}
                    <span
                      className="inline-block"
                      style={{ minWidth: `${gutterWidth}ch` }}
                    >
                      {lineNum}
                    </span>
                  </span>

                  {/* Code content */}
                  <span className="flex-1 whitespace-pre px-4 font-mono">
                    {line}
                  </span>
                </div>

                {/* Tooltip on hover */}
                {lineViolations && hoveredLine === lineNum && (
                  <ViolationTooltip violations={lineViolations} />
                )}
              </div>
            );
          })}
        </code>
      </pre>
    </div>
  );
}
