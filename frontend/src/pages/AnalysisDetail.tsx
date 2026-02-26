/**
 * Analysis detail page — pipeline progress, donut chart, category breakdown,
 * and filterable violation list.
 *
 * Requirements: 8.3, 8.5, 8.6
 */

import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import {
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ArrowLeft,
  Search,
  Code2,
  Download,
} from "lucide-react";
import ExportDialog from "@/components/export/ExportDialog";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { useAnalysis, useViolationReport } from "@/hooks/useAnalysis";
import { cn } from "@/lib/utils";
import {
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  type BCVCategory,
  type AnalysisStatus,
  type Violation,
} from "@/types";

// ---------------------------------------------------------------------------
// Pipeline stages
// ---------------------------------------------------------------------------

const PIPELINE_STAGES = [
  { key: "bce", label: "BCE", description: "Claim Extraction" },
  { key: "dts", label: "DTS", description: "Test Synthesis" },
  { key: "rv", label: "RV", description: "Runtime Verification" },
] as const;

function stageIndex(status: AnalysisStatus): number {
  if (status === "pending") return -1;
  if (status === "bce_running") return 0;
  if (status === "bce_complete") return 0;
  if (status === "dts_running") return 1;
  if (status === "dts_complete") return 1;
  if (status === "rv_running") return 2;
  if (status === "complete") return 3;
  return -1; // failed
}

function isRunning(status: AnalysisStatus): boolean {
  return status.endsWith("_running");
}

// ---------------------------------------------------------------------------
// Pipeline progress indicator
// ---------------------------------------------------------------------------

function PipelineProgress({ status }: { status: AnalysisStatus }) {
  const current = stageIndex(status);
  const running = isRunning(status);
  const failed = status === "failed";

  return (
    <div className="flex items-center gap-2">
      {PIPELINE_STAGES.map((stage, i) => {
        const done = current > i;
        const active = current === i;
        const activeRunning = active && running;

        return (
          <div key={stage.key} className="flex items-center gap-2">
            {i > 0 && (
              <div
                className={cn(
                  "h-0.5 w-8 rounded-full transition-colors duration-500",
                  done ? "bg-emerald-500" : "bg-border",
                )}
              />
            )}
            <div className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-full border-2 text-xs font-bold transition-all duration-500",
                  done && "border-emerald-500 bg-emerald-500 text-white",
                  active && !failed && "border-primary bg-primary text-primary-foreground",
                  activeRunning && "animate-pulse",
                  !done && !active && "border-border text-muted-foreground",
                  failed && active && "border-destructive bg-destructive text-destructive-foreground",
                )}
              >
                {stage.label}
              </div>
              <span className="text-[10px] text-muted-foreground">
                {stage.description}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Donut chart
// ---------------------------------------------------------------------------

function BCVDonutChart({
  breakdown,
}: {
  breakdown: Record<BCVCategory, number>;
}) {
  const data = (Object.keys(breakdown) as BCVCategory[])
    .filter((cat) => breakdown[cat] > 0)
    .map((cat) => ({
      name: CATEGORY_LABELS[cat],
      value: breakdown[cat],
      color: CATEGORY_COLORS[cat],
    }));

  if (data.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No violations detected
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={90}
          paddingAngle={2}
          dataKey="value"
          nameKey="name"
          stroke="none"
        >
          {data.map((entry) => (
            <Cell key={entry.name} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value: number, name: string) => [`${value}`, name]}
          contentStyle={{
            borderRadius: "0.5rem",
            border: "1px solid hsl(var(--border))",
            fontSize: "0.75rem",
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Category breakdown table
// ---------------------------------------------------------------------------

function CategoryBreakdownTable({
  breakdown,
  total,
}: {
  breakdown: Record<BCVCategory, number>;
  total: number;
}) {
  const categories = Object.keys(CATEGORY_LABELS) as BCVCategory[];

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-xs text-muted-foreground">
          <th className="pb-2 font-medium">Category</th>
          <th className="pb-2 text-right font-medium">Count</th>
          <th className="pb-2 text-right font-medium">%</th>
        </tr>
      </thead>
      <tbody>
        {categories.map((cat) => {
          const count = breakdown[cat] ?? 0;
          const pct = total > 0 ? ((count / total) * 100).toFixed(1) : "0.0";
          return (
            <tr key={cat} className="border-b last:border-0">
              <td className="py-2">
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: CATEGORY_COLORS[cat] }}
                  />
                  {CATEGORY_LABELS[cat]}
                </span>
              </td>
              <td className="py-2 text-right font-medium">{count}</td>
              <td className="py-2 text-right text-muted-foreground">{pct}%</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Expandable violation item
// ---------------------------------------------------------------------------

function ViolationItem({ violation }: { violation: Violation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b last:border-0">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left text-sm hover:bg-muted/40"
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-white"
              style={{ backgroundColor: CATEGORY_COLORS[violation.claim.category] }}
            >
              {violation.claim.category}
            </span>
            <span className="truncate font-medium">
              {violation.claim.subject}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {violation.claim.rawText}
          </p>
        </div>
      </button>

      {expanded && (
        <div className="space-y-3 px-4 pb-4 pl-11">
          {violation.testCode && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                Test Code
              </p>
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs leading-relaxed">
                <code>{violation.testCode}</code>
              </pre>
            </div>
          )}
          {violation.traceback && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                Traceback
              </p>
              <pre className="overflow-x-auto rounded-md bg-destructive/5 p-3 text-xs leading-relaxed text-destructive">
                <code>{violation.traceback}</code>
              </pre>
            </div>
          )}
          {(violation.expected || violation.actual) && (
            <div className="flex gap-6 text-xs">
              {violation.expected && (
                <div>
                  <span className="font-medium text-muted-foreground">Expected: </span>
                  <span className="font-mono">{violation.expected}</span>
                </div>
              )}
              {violation.actual && (
                <div>
                  <span className="font-medium text-muted-foreground">Actual: </span>
                  <span className="font-mono">{violation.actual}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filterable violation list grouped by function
// ---------------------------------------------------------------------------

function ViolationList({ violations }: { violations: Violation[] }) {
  const [filter, setFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<BCVCategory | "all">("all");

  const filtered = useMemo(() => {
    let result = violations;
    if (categoryFilter !== "all") {
      result = result.filter((v) => v.claim.category === categoryFilter);
    }
    if (filter.trim()) {
      const q = filter.toLowerCase();
      result = result.filter(
        (v) =>
          v.functionName.toLowerCase().includes(q) ||
          v.claim.rawText.toLowerCase().includes(q) ||
          v.claim.subject.toLowerCase().includes(q),
      );
    }
    return result;
  }, [violations, filter, categoryFilter]);

  // Group by function
  const grouped = useMemo(() => {
    const map = new Map<string, Violation[]>();
    for (const v of filtered) {
      const list = map.get(v.functionName) ?? [];
      list.push(v);
      map.set(v.functionName, list);
    }
    return map;
  }, [filtered]);

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 pb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter violations…"
            className="w-full rounded-lg border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as BCVCategory | "all")}
          className="rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Filter by category"
        >
          <option value="all">All Categories</option>
          {(Object.keys(CATEGORY_LABELS) as BCVCategory[]).map((cat) => (
            <option key={cat} value={cat}>
              {cat} — {CATEGORY_LABELS[cat]}
            </option>
          ))}
        </select>
      </div>

      {/* Grouped list */}
      {grouped.size === 0 && (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No violations match the current filters.
        </p>
      )}

      {Array.from(grouped.entries()).map(([fnName, items]) => (
        <div key={fnName} className="mb-4 rounded-lg border">
          <div className="border-b bg-muted/40 px-4 py-2">
            <span className="text-sm font-semibold font-mono">{fnName}</span>
            <span className="ml-2 text-xs text-muted-foreground">
              {items.length} violation{items.length !== 1 ? "s" : ""}
            </span>
          </div>
          {items.map((v, i) => (
            <ViolationItem key={`${v.functionId}-${v.claim.id}-${i}`} violation={v} />
          ))}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function AnalysisDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: analysis, isLoading, isError } = useAnalysis(id!);
  const { data: report } = useViolationReport(id!);
  const [exportOpen, setExportOpen] = useState(false);

  if (isLoading) {
    return (
      <main className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </main>
    );
  }

  if (isError || !analysis) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-12">
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load analysis.
        </div>
      </main>
    );
  }

  const isComplete = analysis.status === "complete";
  const totalViolations = report
    ? report.violations.length
    : analysis.totalViolations;

  return (
    <main className="mx-auto max-w-4xl px-4 py-12">
      {/* Header */}
      <div className="mb-8">
        <Link
          to="/"
          className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to analyses
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              {analysis.filename ?? "Pasted code"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {analysis.llmProvider} · Created{" "}
              {new Date(analysis.createdAt).toLocaleString()}
            </p>
          </div>
          {isComplete && (
            <div className="flex items-center gap-2">
              <Link
                to={`/analyses/${id}/code`}
                className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm font-medium hover:bg-muted"
              >
                <Code2 className="h-4 w-4" />
                View Code
              </Link>
              <button
                type="button"
                onClick={() => setExportOpen(true)}
                className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm font-medium hover:bg-muted"
              >
                <Download className="h-4 w-4" />
                Export
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Pipeline progress */}
      <section className="mb-8">
        <h2 className="mb-4 text-sm font-medium text-muted-foreground">
          Pipeline Progress
        </h2>
        <PipelineProgress status={analysis.status} />
        {analysis.status === "failed" && (
          <p className="mt-3 text-sm text-destructive">
            Pipeline failed. Please try re-running the analysis.
          </p>
        )}
      </section>

      {/* Results — only shown when complete */}
      {isComplete && report && (
        <>
          {/* Stats row */}
          <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              { label: "Functions", value: report.totalFunctions },
              { label: "Claims", value: report.totalClaims },
              { label: "Violations", value: totalViolations },
              {
                label: "BCV Rate",
                value: `${(report.bcvRate * 100).toFixed(1)}%`,
              },
            ].map((stat) => (
              <div
                key={stat.label}
                className="rounded-lg border bg-card p-4 text-center"
              >
                <p className="text-2xl font-bold">{stat.value}</p>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
              </div>
            ))}
          </div>

          {/* Chart + breakdown */}
          <section className="mb-8 grid gap-6 md:grid-cols-2">
            <div className="rounded-lg border bg-card p-4">
              <h2 className="mb-2 text-sm font-medium">
                Category Distribution
              </h2>
              <BCVDonutChart breakdown={report.categoryBreakdown} />
            </div>
            <div className="rounded-lg border bg-card p-4">
              <h2 className="mb-3 text-sm font-medium">Category Breakdown</h2>
              <CategoryBreakdownTable
                breakdown={report.categoryBreakdown}
                total={totalViolations}
              />
            </div>
          </section>

          {/* Violation list */}
          <section>
            <h2 className="mb-4 text-sm font-medium">Violations</h2>
            <ViolationList violations={report.violations} />
          </section>
        </>
      )}

      {/* In-progress placeholder */}
      {!isComplete && analysis.status !== "failed" && (
        <div className="mt-8 flex flex-col items-center gap-3 py-12 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Analysis in progress — results will appear here when complete.
          </p>
        </div>
      )}

      {/* Export dialog */}
      <ExportDialog
        analysisId={id!}
        open={exportOpen}
        onOpenChange={setExportOpen}
      />
    </main>
  );
}
