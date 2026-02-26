/**
 * Dashboard home page — lists recent analyses with summary cards.
 *
 * Requirements: 8.1
 */

import { Link } from "react-router-dom";
import { Plus, FileCode, Loader2, AlertCircle } from "lucide-react";
import { useAnalysisList } from "@/hooks/useAnalysis";
import { cn } from "@/lib/utils";
import type { Analysis, AnalysisStatus } from "@/types";

// ---------------------------------------------------------------------------
// Status badge config
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<AnalysisStatus, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-muted text-muted-foreground" },
  bce_running: { label: "BCE Running", className: "bg-blue-100 text-blue-700" },
  bce_complete: { label: "BCE Done", className: "bg-blue-100 text-blue-700" },
  dts_running: { label: "DTS Running", className: "bg-violet-100 text-violet-700" },
  dts_complete: { label: "DTS Done", className: "bg-violet-100 text-violet-700" },
  rv_running: { label: "RV Running", className: "bg-amber-100 text-amber-700" },
  complete: { label: "Complete", className: "bg-emerald-100 text-emerald-700" },
  failed: { label: "Failed", className: "bg-destructive/10 text-destructive" },
};

// ---------------------------------------------------------------------------
// Summary card
// ---------------------------------------------------------------------------

function AnalysisSummaryCard({ analysis }: { analysis: Analysis }) {
  const { label, className } = STATUS_CONFIG[analysis.status];
  const bcvPercent = (analysis.bcvRate * 100).toFixed(1);

  return (
    <Link
      to={`/analyses/${analysis.id}`}
      className="block rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-muted/30"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FileCode className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm font-medium">
              {analysis.filename ?? "Pasted code"}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {analysis.llmProvider}
          </p>
        </div>
        <span
          className={cn(
            "inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
            className,
          )}
        >
          {label}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-4 text-sm">
        <span className="text-muted-foreground">
          BCV Rate:{" "}
          <span className="font-medium text-foreground">{bcvPercent}%</span>
        </span>
        <span className="text-muted-foreground">
          Violations:{" "}
          <span className="font-medium text-foreground">
            {analysis.totalViolations}
          </span>
        </span>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardHome() {
  const { data: analyses, isLoading, isError } = useAnalysisList();

  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Analyses</h1>
        <Link
          to="/upload"
          className={cn(
            "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            "bg-primary text-primary-foreground hover:bg-primary/90",
            "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
          )}
        >
          <Plus className="h-4 w-4" />
          New Analysis
        </Link>
      </div>

      {isLoading && (
        <div className="mt-16 flex justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {isError && (
        <div className="mt-8 flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load analyses. Please try again.
        </div>
      )}

      {analyses && analyses.length === 0 && (
        <p className="mt-16 text-center text-muted-foreground">
          No analyses yet.{" "}
          <Link to="/upload" className="text-primary underline underline-offset-4">
            Run your first analysis
          </Link>
        </p>
      )}

      {analyses && analyses.length > 0 && (
        <div className="mt-6 space-y-3">
          {analyses.map((a) => (
            <AnalysisSummaryCard key={a.id} analysis={a} />
          ))}
        </div>
      )}
    </main>
  );
}
