import { motion } from "framer-motion";
import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { deriveStageStates } from "@/lib/pipelineUtils";
import { PIPELINE_STAGES } from "@/lib/constants";
import type { AnalysisStatus, StageState } from "@/types";

interface PipelineStageVizProps { status: AnalysisStatus; }

function StageCard({ stageState }: { stageState: StageState }) {
  const { state, label, fullName, description } = stageState;
  const isActive = state === "active";
  const isComplete = state === "complete";
  const isFailed = state === "failed";
  const isPending = state === "pending";

  return (
    <div className={cn(
      "relative flex flex-col gap-2 rounded-2xl p-4 w-52 transition-all duration-300",
      "glass",
      isActive && "border-indigo-300/60 shadow-[0_0_24px_rgba(99,102,241,0.12),0_8px_32px_rgba(99,102,241,0.06)]",
      isComplete && "border-emerald-300/60 shadow-[0_0_24px_rgba(16,185,129,0.12),0_8px_32px_rgba(16,185,129,0.06)]",
      isFailed && "border-red-300/60 shadow-[0_0_24px_rgba(239,68,68,0.12),0_8px_32px_rgba(239,68,68,0.06)]",
      isPending && "opacity-45",
    )}>
      <div className="flex items-center justify-between">
        <span className={cn(
          "text-xs font-bold tracking-widest uppercase",
          isActive && "text-indigo-600",
          isComplete && "text-emerald-600",
          isFailed && "text-red-600",
          isPending && "text-muted-foreground",
        )}>{label}</span>
        <StatusIcon state={state} />
      </div>
      <p className={cn(
        "text-sm font-semibold leading-tight",
        isActive && "text-indigo-600",
        isComplete && "text-emerald-600",
        isFailed && "text-red-500",
        isPending && "text-muted-foreground",
      )}>{fullName}</p>
      <p className={cn(
        "text-xs leading-snug",
        isActive && "text-indigo-500/70",
        isComplete && "text-emerald-500/70",
        isFailed && "text-red-500/70",
        isPending && "text-muted-foreground/60",
      )}>{description}</p>
    </div>
  );
}

function StatusIcon({ state }: { state: StageState["state"] }) {
  switch (state) {
    case "complete": return <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />;
    case "failed": return <XCircle className="h-5 w-5 text-red-500 shrink-0" />;
    case "active": return <Loader2 className="h-5 w-5 text-indigo-500 shrink-0 animate-spin" />;
    default: return <Clock className="h-5 w-5 text-muted-foreground/40 shrink-0" />;
  }
}

function ArrowConnector({ dimmed }: { dimmed: boolean }) {
  return (
    <div className={cn("flex items-center px-1 shrink-0 transition-opacity duration-300", dimmed ? "opacity-20" : "opacity-60")}>
      <svg width="32" height="16" viewBox="0 0 32 16" fill="none" aria-hidden="true">
        <line x1="0" y1="8" x2="24" y2="8" stroke="currentColor" strokeWidth="2" className="text-foreground/15" />
        <polyline points="18,2 26,8 18,14" stroke="currentColor" strokeWidth="2" fill="none" className="text-foreground/15" />
      </svg>
    </div>
  );
}

export default function PipelineStageVisualization({ status }: PipelineStageVizProps) {
  const stageStates = deriveStageStates(status);
  return (
    <div className="flex items-center justify-center gap-0 flex-wrap">
      {stageStates.map((stageState, idx) => {
        const isLast = idx === PIPELINE_STAGES.length - 1;
        const nextState = stageStates[idx + 1]?.state;
        const arrowDimmed = nextState === "pending";
        return (
          <motion.div
            key={stageState.key}
            initial={{ opacity: 0, y: 16, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 260, damping: 24, delay: idx * 0.08 }}
            className="flex items-center"
          >
            <StageCard stageState={stageState} />
            {!isLast && <ArrowConnector dimmed={arrowDimmed} />}
          </motion.div>
        );
      })}
    </div>
  );
}
