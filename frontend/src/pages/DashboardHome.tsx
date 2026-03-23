import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus, FileCode, Loader2, AlertCircle, Activity, TrendingUp, ShieldAlert, Layers } from "lucide-react";
import { useAnalysisList } from "@/hooks/useAnalysis";
import { SpotlightCard, ShimmerButton, StaggerChildren, StaggerItem } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Analysis, AnalysisStatus } from "@/types";

const STATUS_CONFIG: Record<AnalysisStatus, { label: string; color: string; bg: string; ring: string }> = {
  pending:      { label: "Pending",      color: "text-zinc-500",    bg: "bg-zinc-100",       ring: "ring-zinc-200" },
  bce_running:  { label: "Extracting",   color: "text-blue-600",    bg: "bg-blue-50",        ring: "ring-blue-200" },
  bce_complete: { label: "BCE Done",     color: "text-blue-600",    bg: "bg-blue-50",        ring: "ring-blue-200" },
  dts_running:  { label: "Synthesizing", color: "text-violet-600",  bg: "bg-violet-50",      ring: "ring-violet-200" },
  dts_complete: { label: "DTS Done",     color: "text-violet-600",  bg: "bg-violet-50",      ring: "ring-violet-200" },
  rv_running:   { label: "Verifying",    color: "text-amber-600",   bg: "bg-amber-50",       ring: "ring-amber-200" },
  complete:     { label: "Complete",     color: "text-emerald-600", bg: "bg-emerald-50",     ring: "ring-emerald-200" },
  failed:       { label: "Failed",       color: "text-rose-600",    bg: "bg-rose-50",        ring: "ring-rose-200" },
};

function StatusBadge({ status }: { status: AnalysisStatus }) {
  const c = STATUS_CONFIG[status];
  const isRunning = status.endsWith("_running");
  return (
    <span className={cn("chip ring-1", c.color, c.bg, c.ring)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", c.color.replace("text-", "bg-"), isRunning && "animate-pulse")} />
      {c.label}
    </span>
  );
}

function AnalysisCard({ analysis }: { analysis: Analysis }) {
  const bcvPercent = (analysis.bcvRate * 100).toFixed(1);
  const isComplete = analysis.status === "complete";
  const hasBcv = analysis.totalViolations > 0;

  return (
    <Link to={`/analyses/${analysis.id}`} className="block">
      <SpotlightCard className="glass glass-hover rounded-[var(--radius-2xl)] p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl skeu-raised transition-all duration-300 group-hover:shadow-[0_4px_16px_rgba(99,102,241,0.12)]">
              <FileCode className="h-4 w-4 text-foreground/25" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground/85">
                {analysis.filename ?? "Pasted code"}
              </p>
              <p className="text-[11px] text-muted-foreground/60 mt-0.5 font-medium tracking-wide uppercase">{analysis.llmProvider}</p>
            </div>
          </div>
          <StatusBadge status={analysis.status} />
        </div>

        {isComplete && (
          <div className="mt-4 flex items-center gap-5 pt-4 border-t border-foreground/[0.05]">
            <div className="flex items-center gap-1.5">
              <ShieldAlert className={cn("h-3.5 w-3.5", hasBcv ? "text-rose-500" : "text-emerald-500")} />
              <span className="text-xs text-muted-foreground">
                <span className={cn("font-bold font-mono", hasBcv ? "text-rose-500" : "text-emerald-500")}>
                  {analysis.totalViolations}
                </span>{" "}violations
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <TrendingUp className="h-3.5 w-3.5 text-muted-foreground/40" />
              <span className="text-xs text-muted-foreground">
                <span className="font-bold font-mono text-foreground/70">{bcvPercent}%</span> BCV
              </span>
            </div>
            <div className="ml-auto text-[11px] text-muted-foreground/50 font-medium">
              {new Date(analysis.createdAt).toLocaleDateString()}
            </div>
          </div>
        )}
      </SpotlightCard>
    </Link>
  );
}

export default function DashboardHome() {
  const { data: analyses, isLoading, isError } = useAnalysisList();

  return (
    <div className="min-h-screen relative">
      <div className="fixed top-10 left-[10%] w-[600px] h-[600px] rounded-full bg-indigo-300/20 blur-[160px] pointer-events-none" />
      <div className="fixed bottom-10 right-[5%] w-[500px] h-[500px] rounded-full bg-violet-300/18 blur-[140px] pointer-events-none" />
      <div className="fixed top-[40%] right-[20%] w-[300px] h-[300px] rounded-full bg-blue-200/15 blur-[100px] pointer-events-none" />

      <header className="topbar sticky top-0 z-10">
        <div className="mx-auto max-w-4xl px-4 py-3.5 flex items-center justify-between">
          <motion.div
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="flex items-center gap-2.5"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg skeu-raised">
              <Activity className="h-3.5 w-3.5 text-indigo-500" />
            </div>
            <div>
              <span className="text-sm font-bold tracking-tight text-gradient-primary">VeriDoc</span>
              <p className="text-[9px] text-muted-foreground/50 font-medium tracking-widest uppercase leading-none mt-0.5">Behavioral Contract Verification</p>
            </div>
          </motion.div>
          <Link to="/upload">
            <ShimmerButton>
              <Plus className="h-4 w-4" />
              New Analysis
            </ShimmerButton>
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-10 relative z-[1]">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.05 }}
          className="mb-8"
        >
          <div className="flex items-center gap-1.5 mb-2">
            <Layers className="h-3.5 w-3.5 text-indigo-500" />
            <span className="text-[10px] font-semibold text-indigo-500/60 uppercase tracking-[0.15em]">Dashboard</span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-gradient-primary leading-tight">
            Your Analyses
          </h1>
          <p className="mt-2 text-sm text-muted-foreground max-w-md leading-relaxed">
            Detect docstring hallucinations using behavioral contract verification.
          </p>
        </motion.div>

        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-20"
          >
            <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
            <p className="mt-3 text-sm text-muted-foreground">Loading analyses…</p>
          </motion.div>
        )}

        {isError && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass px-5 py-6 text-center"
          >
            <AlertCircle className="mx-auto mb-2 h-6 w-6 text-rose-500" />
            <p className="text-sm font-medium text-foreground/75">Failed to load analyses</p>
            <p className="mt-1 text-xs text-muted-foreground">Check your connection and try refreshing.</p>
          </motion.div>
        )}

        {!isLoading && !isError && analyses && analyses.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 200, damping: 24 }}
            className="glass-strong px-8 py-14 text-center"
          >
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl skeu-raised">
              <FileCode className="h-6 w-6 text-foreground/20" />
            </div>
            <p className="text-base font-semibold text-foreground/65">No analyses yet</p>
            <p className="mt-1.5 text-sm text-muted-foreground max-w-xs mx-auto">
              Upload a source file, project ZIP, or folder to get started.
            </p>
            <Link to="/upload" className="mt-5 inline-flex">
              <ShimmerButton>
                <Plus className="h-4 w-4" />
                Run Your First Analysis
              </ShimmerButton>
            </Link>
          </motion.div>
        )}

        {!isLoading && !isError && analyses && analyses.length > 0 && (
          <StaggerChildren className="space-y-2.5">
            <StaggerItem>
              <p className="text-[11px] text-muted-foreground/60 font-medium mb-1">
                {analyses.length} {analyses.length === 1 ? "analysis" : "analyses"}
              </p>
            </StaggerItem>
            {analyses.map((analysis) => (
              <StaggerItem key={analysis.id}>
                <AnalysisCard analysis={analysis} />
              </StaggerItem>
            ))}
          </StaggerChildren>
        )}
      </main>
    </div>
  );
}
