import { useState, useEffect, useRef } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Loader2, AlertCircle, CheckCircle2, XCircle,
  ArrowLeft, Download, Activity, Code2, Clock,
  FileCode, ShieldAlert, TrendingUp, Layers,
  Braces, Hash, Timer,
} from "lucide-react";
import ExportDialog from "@/components/export/ExportDialog";
import TabNavigation from "@/components/dashboard/TabNavigation";
import DocumentationTab from "@/components/dashboard/DocumentationTab";
import VerificationTab from "@/components/dashboard/VerificationTab";
import ResearchTab from "@/components/dashboard/ResearchTab";
import { SpotlightCard, AnimatedNumber, StaggerChildren, StaggerItem, ShimmerButton } from "@/components/ui";
import { useAnalysis, useViolationReport, useClaims } from "@/hooks/useAnalysis";
import { cn } from "@/lib/utils";
import type { AnalysisStatus, ClaimGroup, DashboardTab, SupportedLanguage } from "@/types";

/* ── language config ─────────────────────────────────────────────── */
const LANG_META: Record<SupportedLanguage, { label: string; color: string; bg: string; border: string }> = {
  python:     { label: "Python",     color: "text-blue-600",   bg: "bg-blue-50",   border: "border-blue-200" },
  javascript: { label: "JavaScript", color: "text-yellow-600", bg: "bg-yellow-50", border: "border-yellow-200" },
  typescript: { label: "TypeScript", color: "text-blue-500",   bg: "bg-blue-50",   border: "border-blue-200" },
  java:       { label: "Java",       color: "text-orange-600", bg: "bg-orange-50", border: "border-orange-200" },
  go:         { label: "Go",         color: "text-cyan-600",   bg: "bg-cyan-50",   border: "border-cyan-200" },
  rust:       { label: "Rust",       color: "text-red-600",    bg: "bg-red-50",    border: "border-red-200" },
};

/* ── status config ───────────────────────────────────────────────── */
const STATUS_CONFIG: Record<AnalysisStatus, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  pending:      { label: "Pending",      color: "text-zinc-500",    bg: "bg-zinc-100",    icon: <Clock className="h-3 w-3" /> },
  bce_running:  { label: "Extracting",   color: "text-blue-600",    bg: "bg-blue-50",     icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  bce_complete: { label: "BCE Done",     color: "text-blue-600",    bg: "bg-blue-50",     icon: <CheckCircle2 className="h-3 w-3" /> },
  dts_running:  { label: "Synthesizing", color: "text-violet-600",  bg: "bg-violet-50",   icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  dts_complete: { label: "DTS Done",     color: "text-violet-600",  bg: "bg-violet-50",   icon: <CheckCircle2 className="h-3 w-3" /> },
  rv_running:   { label: "Verifying",    color: "text-amber-600",   bg: "bg-amber-50",    icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  complete:     { label: "Complete",     color: "text-emerald-600", bg: "bg-emerald-50",  icon: <CheckCircle2 className="h-3 w-3" /> },
  failed:       { label: "Failed",       color: "text-red-600",     bg: "bg-red-50",      icon: <XCircle className="h-3 w-3" /> },
};

/* ── pipeline progress ───────────────────────────────────────────── */
const PIPELINE_STAGES = [
  { key: "bce", label: "BCE", description: "Claim Extraction" },
  { key: "dts", label: "DTS", description: "Test Synthesis" },
  { key: "rv",  label: "RV",  description: "Runtime Verification" },
] as const;

function stageIndex(status: AnalysisStatus): number {
  if (status === "pending") return -1;
  if (status === "bce_running") return 0;
  if (status === "bce_complete") return 0;
  if (status === "dts_running") return 1;
  if (status === "dts_complete") return 1;
  if (status === "rv_running") return 2;
  if (status === "complete") return 3;
  return -1;
}

function isRunning(status: AnalysisStatus): boolean {
  return status.endsWith("_running");
}

const STATUS_RANGE: Record<AnalysisStatus, { floor: number; ceiling: number }> = {
  pending:      { floor: 0,   ceiling: 2   },
  bce_running:  { floor: 2,   ceiling: 30  },
  bce_complete: { floor: 33,  ceiling: 34  },
  dts_running:  { floor: 34,  ceiling: 63  },
  dts_complete: { floor: 66,  ceiling: 67  },
  rv_running:   { floor: 67,  ceiling: 97  },
  complete:     { floor: 100, ceiling: 100 },
  failed:       { floor: 0,   ceiling: 0   },
};

const CRAWL_SPEED = 0.4;

function PipelineProgress({ status }: { status: AnalysisStatus }) {
  const failed = status === "failed";
  const complete = status === "complete";
  const running = isRunning(status);
  const current = stageIndex(status);
  const { floor, ceiling } = STATUS_RANGE[status];
  const [displayPct, setDisplayPct] = useState(floor);
  const rafRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number | null>(null);

  useEffect(() => {
    setDisplayPct(floor);
    lastTimeRef.current = null;
    if (!running || failed) return;
    const tick = (now: number) => {
      if (lastTimeRef.current === null) lastTimeRef.current = now;
      const delta = (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;
      setDisplayPct((prev) => {
        const next = prev + CRAWL_SPEED * delta;
        return next >= ceiling ? ceiling : next;
      });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const pct = Math.min(displayPct, ceiling);
  const DOT_POSITIONS = [0, 50, 100] as const;

  return (
    <div className="space-y-4">
      <div className="relative h-2.5">
        <div className="h-2.5 w-full rounded-full skeu-inset overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full",
              failed ? "bg-red-500/60" : "bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-400",
            )}
            style={{ width: `${pct}%`, transition: running ? "none" : "width 0.6s ease-out" }}
          />
        </div>
        {running && !failed && (
          <div className="absolute top-0 h-2.5 rounded-full overflow-hidden pointer-events-none" style={{ width: `${pct}%` }}>
            <div className="h-full w-full bg-gradient-to-r from-transparent via-white/30 to-transparent bg-[length:200%_100%] animate-[shimmer_1.8s_linear_infinite]" />
          </div>
        )}
        {PIPELINE_STAGES.map((stage, i) => {
          const pos = DOT_POSITIONS[i];
          const done = current > i || complete;
          const active = current === i && !complete;
          return (
            <div key={stage.key} className="absolute top-1/2" style={{ left: `${pos}%`, transform: "translate(-50%, -50%)" }}>
              <div className={cn(
                "h-5 w-5 rounded-full border-2 transition-all duration-500 flex items-center justify-center",
                done && "bg-emerald-400 border-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.7)]",
                active && !failed && "bg-indigo-400 border-indigo-400 shadow-[0_0_12px_rgba(99,102,241,0.8)] animate-pulse",
                !done && !active && "bg-white border-foreground/10",
                failed && active && "bg-red-500 border-red-500",
              )}>
                {done && <CheckCircle2 className="h-2.5 w-2.5 text-white" />}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex">
        {PIPELINE_STAGES.map((stage, i) => {
          const done = current > i || complete;
          const active = current === i && !complete;
          return (
            <div key={stage.key} className={cn("flex flex-col gap-0.5", i === 0 && "items-start", i === 1 && "items-center flex-1", i === 2 && "items-end ml-auto")}>
              <span className={cn("text-xs font-bold font-mono transition-colors duration-300 flex items-center gap-1",
                done && "text-emerald-600", active && !failed && "text-indigo-600", !done && !active && "text-muted-foreground", failed && active && "text-red-600",
              )}>
                {stage.label}
                {done && <CheckCircle2 className="h-3 w-3" />}
              </span>
              <span className="text-[10px] text-muted-foreground">{stage.description}</span>
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between">
        <span className={cn("text-xs font-medium", failed ? "text-red-600" : complete ? "text-emerald-600" : "text-indigo-600")}>
          {failed && "Pipeline failed"}
          {complete && "All stages complete"}
          {!failed && !complete && running && `${PIPELINE_STAGES[Math.max(0, current)]?.label} in progress…`}
          {!failed && !complete && !running && status === "pending" && "Queued, waiting to start…"}
        </span>
        <span className="text-xs font-mono text-muted-foreground tabular-nums">{Math.round(pct)}%</span>
      </div>
    </div>
  );
}

/* ── helper: elapsed time ────────────────────────────────────────── */
function formatDuration(start: string, end: string | null): string {
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const sec = Math.round((e - s) / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}m ${rem}s`;
}

/* ── mini stat card for the hero row ─────────────────────────────── */
function MiniStat({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1 px-4 py-3">
      <div className="flex items-center gap-1.5 text-muted-foreground/60">
        {icon}
        <span className="text-[10px] font-medium uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-lg font-bold font-mono text-foreground leading-none">
        {children}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                                   */
/* ══════════════════════════════════════════════════════════════════ */

export default function AnalysisDetail() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: analysis, isLoading, isError } = useAnalysis(id!);
  const { data: report, isLoading: isReportLoading, isError: isReportError } = useViolationReport(id!);
  const { data: claimGroups } = useClaims(id!) as { data: ClaimGroup[] | undefined };
  const [exportOpen, setExportOpen] = useState(false);
  const activeTab = (searchParams.get("tab") as DashboardTab) || "verification";
  const [activatedTabs, setActivatedTabs] = useState<Set<DashboardTab>>(() => new Set([activeTab]));

  const handleTabChange = (tab: DashboardTab) => {
    setSearchParams({ tab });
    setActivatedTabs((prev) => {
      if (prev.has(tab)) return prev;
      const next = new Set(prev);
      next.add(tab);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !analysis) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <div className="flex items-center gap-2 rounded-2xl glass px-4 py-3 text-sm text-red-600">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load analysis.
        </div>
      </div>
    );
  }

  const isComplete = analysis.status === "complete";
  const isFailed = analysis.status === "failed";
  const statusCfg = STATUS_CONFIG[analysis.status];
  const langMeta = LANG_META[analysis.language];
  const hasBcv = analysis.totalViolations > 0;
  const bcvPercent = analysis.bcvRate * 100;

  return (
    <div className="min-h-screen relative">
      {/* Background orbs */}
      <div className="fixed top-0 left-0 w-[600px] h-[600px] rounded-full bg-indigo-300/20 blur-[140px] pointer-events-none" />
      <div className="fixed bottom-0 right-0 w-[500px] h-[500px] rounded-full bg-violet-300/18 blur-[140px] pointer-events-none" />
      <div className="fixed top-[50%] left-[60%] w-[300px] h-[300px] rounded-full bg-blue-200/12 blur-[100px] pointer-events-none" />

      {/* ── Topbar ──────────────────────────────────────────────── */}
      <header className="topbar sticky top-0 z-10">
        <div className="mx-auto max-w-4xl px-4 py-3.5 flex items-center justify-between">
          <Link to="/" className="btn-tertiary">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Link>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg skeu-raised">
              <Activity className="h-3.5 w-3.5 text-indigo-500" />
            </div>
            <span className="text-sm font-bold tracking-tight text-gradient-primary">VeriDoc</span>
          </div>
          {isComplete && (
            <div className="flex items-center gap-2">
              <Link to={`/analyses/${id}/code`} className="btn-secondary btn-sm">
                <Code2 className="h-3.5 w-3.5" />
                Code
              </Link>
              <button type="button" onClick={() => setExportOpen(true)} className="btn-secondary btn-sm">
                <Download className="h-3.5 w-3.5" />
                Export
              </button>
            </div>
          )}
          {!isComplete && <div />}
        </div>
      </header>

      {/* ── Main content ────────────────────────────────────────── */}
      <main className="mx-auto max-w-4xl px-4 py-8 relative z-[1]">

        {/* ── Hero card ─────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24 }}
          className="mb-6"
        >
          <SpotlightCard className="rounded-[var(--radius-2xl)] glass p-6">
            <div className="flex items-start gap-4">
              {/* File icon */}
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl skeu-raised">
                <FileCode className="h-6 w-6 text-indigo-500/70" />
              </div>

              {/* File info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2.5 flex-wrap mb-1">
                  <h1 className="text-xl font-bold tracking-tight text-foreground">
                    {analysis.filename ?? "Pasted code"}
                  </h1>
                  {/* Language badge */}
                  {langMeta && (
                    <span className={cn("inline-flex items-center gap-1 rounded-lg px-2 py-0.5 text-[10px] font-bold border", langMeta.color, langMeta.bg, langMeta.border)}>
                      <Braces className="h-2.5 w-2.5" />
                      {langMeta.label}
                    </span>
                  )}
                  {/* Status badge */}
                  <span className={cn("inline-flex items-center gap-1 rounded-lg px-2 py-0.5 text-[10px] font-bold", statusCfg.color, statusCfg.bg)}>
                    {statusCfg.icon}
                    {statusCfg.label}
                  </span>
                </div>

                <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                  <span className="flex items-center gap-1">
                    <Layers className="h-3 w-3" />
                    {analysis.llmProvider}
                  </span>
                  <span className="text-foreground/10">·</span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {new Date(analysis.createdAt).toLocaleString()}
                  </span>
                  {analysis.completedAt && (
                    <>
                      <span className="text-foreground/10">·</span>
                      <span className="flex items-center gap-1">
                        <Timer className="h-3 w-3" />
                        {formatDuration(analysis.createdAt, analysis.completedAt)}
                      </span>
                    </>
                  )}
                </div>

                {/* Action buttons for complete state — inline in hero */}
                {isComplete && (
                  <div className="flex items-center gap-2 mt-4">
                    <Link to={`/analyses/${id}/code`}>
                      <ShimmerButton className="btn-sm text-xs">
                        <Code2 className="h-3.5 w-3.5" />
                        View Annotated Code
                      </ShimmerButton>
                    </Link>
                    <button type="button" onClick={() => setExportOpen(true)} className="btn-secondary btn-sm">
                      <Download className="h-3.5 w-3.5" />
                      Export Report
                    </button>
                  </div>
                )}
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        {/* ── Quick stats row (visible when analysis has data) ─── */}
        {(isComplete || analysis.totalFunctions > 0) && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.06 }}
            className="mb-6"
          >
            <StaggerChildren className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StaggerItem>
                <SpotlightCard className="rounded-[var(--radius-2xl)] glass stat-accent">
                  <MiniStat icon={<Hash className="h-3 w-3" />} label="Functions">
                    <AnimatedNumber value={analysis.totalFunctions} />
                  </MiniStat>
                </SpotlightCard>
              </StaggerItem>
              <StaggerItem>
                <SpotlightCard className="rounded-[var(--radius-2xl)] glass stat-accent">
                  <MiniStat icon={<Layers className="h-3 w-3" />} label="Claims">
                    <AnimatedNumber value={analysis.totalClaims} />
                  </MiniStat>
                </SpotlightCard>
              </StaggerItem>
              <StaggerItem>
                <SpotlightCard className="rounded-[var(--radius-2xl)] glass stat-accent">
                  <MiniStat icon={<ShieldAlert className="h-3 w-3" />} label="Violations">
                    <span className={cn(hasBcv ? "text-red-600" : "text-emerald-600")}>
                      <AnimatedNumber value={analysis.totalViolations} />
                    </span>
                  </MiniStat>
                </SpotlightCard>
              </StaggerItem>
              <StaggerItem>
                <SpotlightCard className="rounded-[var(--radius-2xl)] glass stat-accent">
                  <MiniStat icon={<TrendingUp className="h-3 w-3" />} label="BCV Rate">
                    <AnimatedNumber value={bcvPercent} decimals={1} suffix="%" />
                  </MiniStat>
                </SpotlightCard>
              </StaggerItem>
            </StaggerChildren>
          </motion.div>
        )}

        {/* ── Pipeline progress ──────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.12 }}
          className="mb-6 rounded-[var(--radius-2xl)] glass p-6"
        >
          <div className="flex items-center justify-between mb-5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Pipeline Progress</p>
            <span className={cn(
              "inline-flex items-center gap-1.5 text-xs font-semibold",
              isFailed ? "text-red-600" : isComplete ? "text-emerald-600" : "text-indigo-600",
            )}>
              {isComplete && <><CheckCircle2 className="h-3.5 w-3.5" /> All stages complete</>}
              {isFailed && <><XCircle className="h-3.5 w-3.5" /> Pipeline failed</>}
              {!isComplete && !isFailed && <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Processing</>}
            </span>
          </div>
          <PipelineProgress status={analysis.status} />
          {isFailed && (
            <div className="mt-4 rounded-xl bg-red-50 border border-red-200/60 px-4 py-3 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
              <p className="text-sm text-red-600">Pipeline failed. Please try re-running the analysis.</p>
            </div>
          )}
        </motion.section>

        {/* ── Tab navigation ─────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.18 }}
          className="mb-6"
        >
          <TabNavigation analysisId={id!} analysis={analysis} activeTab={activeTab} onTabChange={handleTabChange} />
        </motion.div>

        {/* ── Tab content ────────────────────────────────────────── */}
        <div className={activeTab === "documentation" ? "block" : "hidden"}>
          {activatedTabs.has("documentation") && <DocumentationTab analysisId={id!} analysisStatus={analysis.status} />}
        </div>
        <div className={activeTab === "verification" ? "block" : "hidden"}>
          {activatedTabs.has("verification") && (
            <VerificationTab analysis={analysis} report={report} claimGroups={claimGroups} isReportLoading={isReportLoading} isReportError={isReportError} />
          )}
        </div>
        <div className={activeTab === "research" ? "block" : "hidden"}>
          {activatedTabs.has("research") && <ResearchTab />}
        </div>
      </main>

      <ExportDialog analysisId={id!} open={exportOpen} onOpenChange={setExportOpen} />
    </div>
  );
}
