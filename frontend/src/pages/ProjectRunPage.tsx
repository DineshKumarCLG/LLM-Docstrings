import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Activity, Loader2, AlertCircle, CheckCircle2, XCircle, FileCode, ShieldAlert } from "lucide-react";
import { useBatch } from "@/hooks/useAnalysis";
import { AnimatedNumber, StaggerChildren, StaggerItem } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Analysis, AnalysisStatus } from "@/types";

const STATUS_CONFIG: Record<AnalysisStatus, { label: string; dot: string; text: string }> = {
  pending:      { label: "Queued",       dot: "bg-zinc-400",                 text: "text-zinc-500" },
  bce_running:  { label: "Extracting",   dot: "bg-blue-500 animate-pulse",   text: "text-blue-600" },
  bce_complete: { label: "BCE Done",     dot: "bg-blue-500",                 text: "text-blue-600" },
  dts_running:  { label: "Synthesizing", dot: "bg-violet-500 animate-pulse", text: "text-violet-600" },
  dts_complete: { label: "DTS Done",     dot: "bg-violet-500",               text: "text-violet-600" },
  rv_running:   { label: "Verifying",    dot: "bg-amber-500 animate-pulse",  text: "text-amber-600" },
  complete:     { label: "Complete",     dot: "bg-emerald-500",              text: "text-emerald-600" },
  failed:       { label: "Failed",       dot: "bg-red-500",                  text: "text-red-600" },
};

function StatusBadge({ status }: { status: AnalysisStatus }) {
  const { label, dot, text } = STATUS_CONFIG[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium bg-foreground/[0.03] border border-foreground/[0.06]", text)}>
      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", dot)} />
      {label}
    </span>
  );
}

function FileRow({ analysis }: { analysis: Analysis }) {
  const isComplete = analysis.status === "complete";
  const isFailed = analysis.status === "failed";
  const hasBcv = analysis.totalViolations > 0;

  return (
    <Link
      to={`/analyses/${analysis.id}`}
      className={cn(
        "group flex items-center gap-4 rounded-2xl px-4 py-3.5 animate-fade-in",
        "glass glass-hover card-lift",
        isFailed && "opacity-60",
      )}
    >
      <div className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl skeu-raised transition-all duration-200",
        isComplete && !hasBcv && "border-emerald-500/20",
        isComplete && hasBcv && "border-red-500/20",
      )}>
        {isComplete && !hasBcv && <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
        {isComplete && hasBcv && <ShieldAlert className="h-4 w-4 text-red-600" />}
        {isFailed && <XCircle className="h-4 w-4 text-red-600" />}
        {!isComplete && !isFailed && <FileCode className="h-4 w-4 text-muted-foreground" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground font-mono">{analysis.filename ?? "unknown.py"}</p>
        {isComplete && (
          <div className="mt-0.5 flex items-center gap-3">
            <span className="text-xs text-muted-foreground"><span className={cn("font-semibold font-mono", hasBcv ? "text-red-600" : "text-emerald-600")}>{analysis.totalViolations}</span> violations</span>
            <span className="text-xs text-muted-foreground"><span className="font-semibold font-mono text-foreground">{(analysis.bcvRate * 100).toFixed(1)}%</span> BCV</span>
            <span className="text-xs text-muted-foreground">{analysis.totalFunctions} fn · {analysis.totalClaims} claims</span>
          </div>
        )}
      </div>
      <StatusBadge status={analysis.status} />
    </Link>
  );
}

function BatchSummaryBar({ total, complete, failed, inProgress }: { total: number; complete: number; failed: number; inProgress: number }) {
  const completePct = total > 0 ? (complete / total) * 100 : 0;
  const failedPct = total > 0 ? (failed / total) * 100 : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 24 }}
      className="rounded-2xl glass p-5 space-y-4"
    >
      <div className="flex items-center gap-6">
        <div className="text-center">
          <p className="text-2xl font-bold font-mono text-foreground"><AnimatedNumber value={total} /></p>
          <p className="text-xs text-muted-foreground">Total files</p>
        </div>
        <div className="text-center">
          <p className="text-2xl font-bold font-mono text-emerald-600"><AnimatedNumber value={complete} /></p>
          <p className="text-xs text-muted-foreground">Complete</p>
        </div>
        <div className="text-center">
          <p className="text-2xl font-bold font-mono text-blue-600"><AnimatedNumber value={inProgress} /></p>
          <p className="text-xs text-muted-foreground">In progress</p>
        </div>
        {failed > 0 && (
          <div className="text-center">
            <p className="text-2xl font-bold font-mono text-red-600"><AnimatedNumber value={failed} /></p>
            <p className="text-xs text-muted-foreground">Failed</p>
          </div>
        )}
      </div>
      <div className="h-2 w-full rounded-full skeu-inset overflow-hidden flex">
        <motion.div
          className="h-full bg-gradient-to-r from-indigo-400 to-violet-400"
          initial={{ width: 0 }}
          animate={{ width: `${completePct}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 20, delay: 0.2 }}
        />
        {failedPct > 0 && (
          <motion.div
            className="h-full bg-red-500/60"
            initial={{ width: 0 }}
            animate={{ width: `${failedPct}%` }}
            transition={{ type: "spring", stiffness: 80, damping: 20, delay: 0.3 }}
          />
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {inProgress > 0 ? `${inProgress} file${inProgress !== 1 ? "s" : ""} still running…` : complete === total ? "All files analysed" : `${complete} of ${total} complete`}
      </p>
    </motion.div>
  );
}

export default function ProjectRunPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const { data: batch, isLoading, isError } = useBatch(batchId ?? null);

  return (
    <div className="min-h-screen relative">
      <div className="fixed top-0 right-0 w-[600px] h-[600px] rounded-full bg-indigo-300/20 blur-[140px] pointer-events-none" />
      <div className="fixed bottom-0 left-0 w-[500px] h-[500px] rounded-full bg-violet-300/18 blur-[140px] pointer-events-none" />
      <header className="topbar sticky top-0 z-10">
        <div className="mx-auto max-w-4xl px-4 py-4 flex items-center justify-between">
          <Link to="/" className="btn-tertiary"><ArrowLeft className="h-4 w-4" /> Back</Link>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg skeu-raised"><Activity className="h-3.5 w-3.5 text-indigo-500" /></div>
            <span className="text-sm font-bold">VeriDoc</span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-10 relative z-[1]">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24 }}
          className="mb-8"
        >
          <h1 className="text-2xl font-bold tracking-tight text-gradient-teal">Project Analysis</h1>
          <p className="mt-1 text-xs text-muted-foreground font-mono">{batchId}</p>
        </motion.div>
        {isLoading && <div className="flex justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>}
        {isError && (
          <div className="flex items-center gap-2 rounded-2xl glass px-4 py-3 text-sm text-red-600">
            <AlertCircle className="h-4 w-4 shrink-0" /> Failed to load batch.
          </div>
        )}
        {batch && (
          <div className="space-y-4">
            <BatchSummaryBar total={batch.total} complete={batch.complete} failed={batch.failed} inProgress={batch.in_progress} />
            <StaggerChildren className="space-y-2">
              {batch.analyses.map((a) => (
                <StaggerItem key={a.id}>
                  <FileRow analysis={a} />
                </StaggerItem>
              ))}
            </StaggerChildren>
          </div>
        )}
      </main>
    </div>
  );
}
