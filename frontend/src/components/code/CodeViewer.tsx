import { useState, useMemo } from "react";
import { CATEGORY_COLORS, CATEGORY_LABELS, type Violation } from "@/types";

interface CodeViewerProps { sourceCode: string; violations: Violation[]; }

function buildLineViolationMap(violations: Violation[]) {
  const map = new Map<number, Violation[]>();
  for (const v of violations) {
    if (v.claim.sourceLine > 0) {
      const list = map.get(v.claim.sourceLine) ?? [];
      list.push(v);
      map.set(v.claim.sourceLine, list);
    }
  }
  return map;
}

function ViolationTooltip({ violations }: { violations: Violation[] }) {
  return (
    <div className="absolute left-full top-0 z-50 ml-3 w-80 rounded-2xl glass-strong p-3 shadow-2xl shadow-black/40">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {violations.length} violation{violations.length !== 1 ? "s" : ""} on this line
      </p>
      <div className="space-y-2">
        {violations.map((v, i) => (
          <div key={i} className="rounded-xl glass p-2.5 text-xs">
            <div className="mb-1.5 flex items-center gap-2">
              <span className="inline-flex items-center rounded-lg px-1.5 py-0.5 text-[10px] font-bold text-white" style={{ backgroundColor: CATEGORY_COLORS[v.claim.category] }}>{v.claim.category}</span>
              <span className="font-medium text-foreground">{CATEGORY_LABELS[v.claim.category]}</span>
            </div>
            <p className="text-muted-foreground">{v.claim.rawText}</p>
            {v.expected && <p className="mt-1 text-xs"><span className="font-medium text-muted-foreground">Expected: </span><span className="font-mono text-foreground">{v.expected}</span></p>}
            {v.actual && <p className="text-xs"><span className="font-medium text-muted-foreground">Actual: </span><span className="font-mono text-foreground">{v.actual}</span></p>}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CodeViewer({ sourceCode, violations }: CodeViewerProps) {
  const [hoveredLine, setHoveredLine] = useState<number | null>(null);
  const lines = useMemo(() => sourceCode.split("\n"), [sourceCode]);
  const lineViolationMap = useMemo(() => buildLineViolationMap(violations), [violations]);
  const gutterWidth = String(lines.length).length;

  return (
    <div className="overflow-x-auto rounded-2xl glass">
      <pre className="text-sm leading-6">
        <code>
          {lines.map((line, idx) => {
            const lineNum = idx + 1;
            const lineViolations = lineViolationMap.get(lineNum);
            return (
              <div key={lineNum} className="relative"
                onMouseEnter={() => lineViolations && setHoveredLine(lineNum)}
                onMouseLeave={() => setHoveredLine(null)}>
                <div className={lineViolations ? "flex bg-red-500/[0.06] hover:bg-red-500/[0.10]" : "flex hover:bg-foreground/[0.02]"}>
                  <span className="sticky left-0 flex shrink-0 select-none items-center gap-1.5 border-r border-foreground/[0.06] bg-foreground/[0.02] px-3 text-right text-xs text-muted-foreground/40">
                    {lineViolations?.[0] && <span className="inline-block h-1.5 w-1.5 rounded-full shrink-0" style={{ backgroundColor: CATEGORY_COLORS[lineViolations[0].claim.category] }} aria-label={`Violation: ${lineViolations[0].claim.category}`} />}
                    <span className="inline-block" style={{ minWidth: `${gutterWidth}ch` }}>{lineNum}</span>
                  </span>
                  <span className="flex-1 whitespace-pre px-4 font-mono text-foreground/85">{line}</span>
                </div>
                {lineViolations && hoveredLine === lineNum && <ViolationTooltip violations={lineViolations} />}
              </div>
            );
          })}
        </code>
      </pre>
    </div>
  );
}
