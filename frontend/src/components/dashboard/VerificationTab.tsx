import { useState } from "react";
import { motion } from "framer-motion";
import { Search, Code2, FileText, AlertCircle, Activity, Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { AnimatedNumber, SpotlightCard, StaggerChildren, StaggerItem } from "@/components/ui";
import PipelineStageVisualization from "@/components/dashboard/PipelineStageVisualization";
import TaxonomyReferenceTable from "@/components/dashboard/TaxonomyReferenceTable";
import CategoryBreakdownChips from "@/components/dashboard/CategoryBreakdownChips";
import PerFunctionResults from "@/components/dashboard/PerFunctionResults";
import type { Analysis, ViolationReport, ClaimGroup, BCVCategory } from "@/types";

export interface VerificationTabProps {
  analysis: Analysis;
  report: ViolationReport | undefined;
  claimGroups: ClaimGroup[] | undefined;
  isReportLoading?: boolean;
  isReportError?: boolean;
}

const STAT_META: Record<string, { icon: React.ReactNode; color: string }> = {
  Functions: { icon: <Code2 className="h-4 w-4" />, color: "text-indigo-600 bg-indigo-50/80 border-indigo-200/60" },
  Claims: { icon: <FileText className="h-4 w-4" />, color: "text-violet-600 bg-violet-50/80 border-violet-200/60" },
  Violations: { icon: <AlertCircle className="h-4 w-4" />, color: "text-red-600 bg-red-50/80 border-red-200/60" },
  "BCV Rate": { icon: <Activity className="h-4 w-4" />, color: "text-amber-600 bg-amber-50/80 border-amber-200/60" },
};

function StatCard({ label, value }: { label: string; value: string | number }) {
  const meta = STAT_META[label];
  const isPercentage = typeof value === "string" && value.endsWith("%");
  const numericValue = isPercentage ? parseFloat(value) : typeof value === "number" ? value : 0;

  return (
    <SpotlightCard className="rounded-[var(--radius-2xl)] glass card-lift stat-accent cursor-default">
      <div className="relative p-5 overflow-hidden">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[40px] font-bold leading-none tracking-tight text-foreground font-mono">
              <AnimatedNumber
                value={numericValue}
                decimals={isPercentage ? 1 : 0}
                suffix={isPercentage ? "%" : ""}
              />
            </p>
            <p className="mt-2 text-xs font-medium text-muted-foreground">{label}</p>
          </div>
          {meta && (
            <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border", meta.color)}>
              {meta.icon}
            </div>
          )}
        </div>
      </div>
    </SpotlightCard>
  );
}

export default function VerificationTab({
  analysis, report, claimGroups, isReportLoading = false, isReportError = false,
}: VerificationTabProps) {
  const [categoryFilter, setCategoryFilter] = useState<BCVCategory | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const isComplete = analysis.status === "complete";
  const highlightCategories: BCVCategory[] = report
    ? (Object.keys(report.categoryBreakdown) as BCVCategory[]).filter((cat) => report.categoryBreakdown[cat] > 0)
    : [];
  const hasNoViolations = isComplete && report != null && report.violations.length === 0;

  return (
    <div className="space-y-6">
      <PipelineStageVisualization status={analysis.status} />

      {isComplete && isReportError && !report && (
        <div className="rounded-2xl glass px-6 py-10 text-center border-red-500/20">
          <AlertCircle className="mx-auto mb-3 h-8 w-8 text-red-500" aria-hidden="true" />
          <p className="text-sm font-medium text-foreground">Failed to load verification results</p>
          <p className="mt-1 text-xs text-muted-foreground">A network error occurred. TanStack Query will retry automatically.</p>
        </div>
      )}

      {isComplete && isReportLoading && !report && !isReportError && (
        <div className="rounded-2xl glass px-6 py-10 text-center">
          <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-muted-foreground" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">Loading verification results…</p>
        </div>
      )}

      {hasNoViolations && (
        <>
          <StaggerChildren className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StaggerItem><StatCard label="Functions" value={report!.totalFunctions} /></StaggerItem>
            <StaggerItem><StatCard label="Claims" value={report!.totalClaims} /></StaggerItem>
            <StaggerItem><StatCard label="Violations" value={0} /></StaggerItem>
            <StaggerItem><StatCard label="BCV Rate" value={`${(report!.bcvRate * 100).toFixed(1)}%`} /></StaggerItem>
          </StaggerChildren>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.3 }}
            className="rounded-2xl glass px-6 py-10 text-center"
          >
            <CheckCircle2 className="mx-auto mb-3 h-8 w-8 text-emerald-500" aria-hidden="true" />
            <p className="text-sm font-medium text-foreground">No violations detected</p>
            <p className="mt-1 text-xs text-muted-foreground">All claims passed verification.</p>
          </motion.div>
        </>
      )}

      {isComplete && report && !hasNoViolations ? (
        <>
          <StaggerChildren className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StaggerItem><StatCard label="Functions" value={report.totalFunctions} /></StaggerItem>
            <StaggerItem><StatCard label="Claims" value={report.totalClaims} /></StaggerItem>
            <StaggerItem><StatCard label="Violations" value={report.violations.length} /></StaggerItem>
            <StaggerItem><StatCard label="BCV Rate" value={`${(report.bcvRate * 100).toFixed(1)}%`} /></StaggerItem>
          </StaggerChildren>
          <TaxonomyReferenceTable highlightCategories={highlightCategories} />
          <div className="space-y-3">
            <CategoryBreakdownChips breakdown={report.categoryBreakdown} activeFilter={categoryFilter} onFilterChange={setCategoryFilter} />
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" aria-hidden="true" />
              <input
                type="search"
                placeholder="Search by function name, claim text, or subject…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="input pl-9 pr-4 py-2.5"
                aria-label="Search verification results"
              />
            </div>
          </div>
          <PerFunctionResults violations={report.violations} claimGroups={claimGroups ?? []} categoryFilter={categoryFilter} searchQuery={searchQuery} />
        </>
      ) : (
        !isComplete && (
          <div className="rounded-2xl glass px-6 py-10 text-center">
            <p className="text-sm font-medium text-muted-foreground">
              {analysis.status === "failed"
                ? "Pipeline failed — no verification results available."
                : "Analysis in progress — results will appear once the pipeline completes."}
            </p>
          </div>
        )
      )}
    </div>
  );
}
