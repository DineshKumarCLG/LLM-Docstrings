import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { aggregateFunctionResults } from "@/lib/aggregateResults";
import { CATEGORY_COLORS, CATEGORY_LABELS } from "@/types";
import type { BCVCategory, ClaimGroup, FunctionVerificationResult, Violation } from "@/types";

interface PerFunctionResultsProps {
  violations: Violation[];
  claimGroups: ClaimGroup[];
  categoryFilter: BCVCategory | "all";
  searchQuery: string;
}

function CountPill({ count, variant }: { count: number; variant: "pass" | "fail" }) {
  const isPass = variant === "pass";
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
      isPass ? "bg-emerald-500/15 text-emerald-600 border border-emerald-500/20" : "bg-red-500/15 text-red-600 border border-red-500/20",
    )}>
      {isPass ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {count}
    </span>
  );
}

function FunctionDetail({ result }: { result: FunctionVerificationResult }) {
  const violationsByClaimId = useMemo(() => {
    const map = new Map<string, Violation>();
    for (const v of result.violations) map.set(v.claim.id, v);
    return map;
  }, [result.violations]);

  return (
    <div className="border-t border-foreground/[0.05] bg-foreground/[0.02] px-4 py-3 space-y-3">
      {result.claims.map((claim) => {
        const violation = violationsByClaimId.get(claim.id);
        const failed = Boolean(violation);
        const color = CATEGORY_COLORS[claim.category];
        return (
          <div key={claim.id} className={cn("rounded-xl p-3 text-sm glass", failed ? "border-red-500/15" : "border-emerald-500/15")}>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="shrink-0 inline-flex items-center rounded-lg px-1.5 py-0.5 text-xs font-bold text-white" style={{ backgroundColor: color }} title={CATEGORY_LABELS[claim.category]}>{claim.category}</span>
      <span className={cn("font-medium", failed ? "text-red-600" : "text-emerald-600")}>{claim.rawText}</span>
              <span className="ml-auto shrink-0">
                {failed
                  ? <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-600"><XCircle className="h-3.5 w-3.5" /> FAIL</span>
                  : <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600"><CheckCircle2 className="h-3.5 w-3.5" /> PASS</span>
                }
              </span>
            </div>
            {claim.subject && <p className="mt-1 text-xs text-muted-foreground">Subject: <span className="font-mono">{claim.subject}</span></p>}
            {failed && violation && (
              <div className="mt-2 space-y-2">
                {violation.testCode && (
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground mb-1">Test code</p>
                    <pre className="overflow-x-auto rounded-lg skeu-inset p-3 text-xs text-emerald-700 leading-relaxed">{violation.testCode}</pre>
                  </div>
                )}
                {violation.traceback && (
                  <div>
                    <p className="text-xs font-semibold text-red-600 mb-1">Traceback</p>
                    <pre className="overflow-x-auto rounded-lg skeu-inset p-3 text-xs text-red-700 leading-relaxed">{violation.traceback}</pre>
                  </div>
                )}
                {(violation.expected || violation.actual) && (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {violation.expected && (
                      <div>
                        <p className="font-semibold text-muted-foreground mb-0.5">Expected</p>
                        <code className="block rounded-lg skeu-inset px-2 py-1 font-mono text-foreground/80">{violation.expected}</code>
                      </div>
                    )}
                    {violation.actual && (
                      <div>
                        <p className="font-semibold text-red-600 mb-0.5">Actual</p>
                        <code className="block rounded-lg skeu-inset px-2 py-1 font-mono text-red-700">{violation.actual}</code>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function PerFunctionResults({ violations, claimGroups, categoryFilter, searchQuery }: PerFunctionResultsProps) {
  const [expandedFunctions, setExpandedFunctions] = useState<Set<string>>(new Set());
  const allResults = useMemo(() => aggregateFunctionResults(violations, claimGroups), [violations, claimGroups]);

  const filteredResults = useMemo(() => {
    let results = allResults;
    if (categoryFilter !== "all") {
      results = results
        .map((r) => ({
          ...r,
          violations: r.violations.filter((v) => v.claim.category === categoryFilter),
          claims: r.claims.filter((c) => !r.violations.some((v) => v.claim.id === c.id) || c.category === categoryFilter),
        }))
        .filter((r) => r.violations.length > 0);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      results = results.filter((r) =>
        r.functionName.toLowerCase().includes(q) ||
        r.claims.some((c) => c.rawText.toLowerCase().includes(q) || c.subject.toLowerCase().includes(q)),
      );
    }
    return results;
  }, [allResults, categoryFilter, searchQuery]);

  const toggleExpanded = (functionName: string) => {
    setExpandedFunctions((prev) => {
      const next = new Set(prev);
      if (next.has(functionName)) next.delete(functionName);
      else next.add(functionName);
      return next;
    });
  };

  if (violations.length === 0 && claimGroups.length === 0) {
    return (
      <div className="rounded-2xl glass px-6 py-10 text-center">
        <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-emerald-500" aria-hidden="true" />
        <p className="text-sm font-medium">No violations detected</p>
      </div>
    );
  }

  if (filteredResults.length === 0) {
    return (
      <div className="rounded-2xl glass px-6 py-10 text-center">
        <p className="text-sm font-medium text-muted-foreground">No results match filters</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl glass overflow-hidden">
      <div className="px-4 py-3 border-b border-foreground/[0.06]">
        <h3 className="text-sm font-semibold text-foreground/80 uppercase tracking-wide">
          Per-Function Results
          <span className="ml-2 text-xs font-normal text-muted-foreground normal-case">
            ({filteredResults.length} function{filteredResults.length !== 1 ? "s" : ""})
          </span>
        </h3>
      </div>
      <div className="divide-y divide-foreground/[0.05]">
        {filteredResults.map((result) => {
          const isExpanded = expandedFunctions.has(result.functionName);
          return (
            <div key={result.functionName}>
              <button
                type="button"
                className={cn(
                  "w-full flex items-center gap-3 px-4 py-3 text-left",
                  "hover:bg-foreground/[0.03] transition-colors duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500/30",
                )}
                onClick={() => toggleExpanded(result.functionName)}
                aria-expanded={isExpanded}
              >
                <motion.span
                  animate={{ rotate: isExpanded ? 90 : 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 25 }}
                  className="shrink-0 text-muted-foreground"
                >
                  <ChevronRight className="h-4 w-4" />
                </motion.span>
                <span className="flex-1 min-w-0 font-mono text-sm font-medium text-foreground/90 truncate">{result.functionName}</span>
                <div className="shrink-0 flex items-center gap-2">
                  <CountPill count={result.passCount} variant="pass" />
                  <CountPill count={result.failCount} variant="fail" />
                </div>
              </button>
              <AnimatePresence initial={false}>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    className="overflow-hidden"
                  >
                    <FunctionDetail result={result} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}
