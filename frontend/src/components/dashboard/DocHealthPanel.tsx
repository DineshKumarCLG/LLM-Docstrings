import { useQuery } from "@tanstack/react-query";
import { 
  FileText, 
  AlertTriangle, 
  CheckCircle2, 
  XCircle,
  TrendingUp,
  Loader2,
  FileQuestion,
  Layers,
  Activity
} from "lucide-react";
import { cn } from "@/lib/utils";
import { analysisApi } from "@/api/client";
import type { FunctionHealth } from "@/types";
import { CATEGORY_COLORS, type BCVCategory } from "@/types";

interface DocHealthPanelProps {
  analysisId: string;
}

function HealthGauge({ score, size = "lg" }: { score: number; size?: "sm" | "lg" }) {
  const radius = size === "lg" ? 60 : 30;
  const strokeWidth = size === "lg" ? 10 : 6;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  
  const getColor = (s: number) => {
    if (s >= 80) return "#22c55e";
    if (s >= 60) return "#eab308";
    if (s >= 40) return "#f97316";
    return "#ef4444";
  };

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg 
        width={radius * 2 + strokeWidth * 2} 
        height={radius * 2 + strokeWidth * 2}
        className="transform -rotate-90"
      >
        <circle
          cx={radius + strokeWidth}
          cy={radius + strokeWidth}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={radius + strokeWidth}
          cy={radius + strokeWidth}
          r={radius}
          fill="none"
          stroke={getColor(score)}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          className="transition-all duration-1000"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={cn(
          "font-bold",
          size === "lg" ? "text-3xl" : "text-lg"
        )}>
          {score}
        </span>
      </div>
    </div>
  );
}

function MetricCard({ 
  icon, 
  label, 
  value, 
  subValue,
  color = "primary" 
}: { 
  icon: React.ReactNode; 
  label: string; 
  value: string | number;
  subValue?: string;
  color?: "primary" | "success" | "warning" | "danger";
}) {
  const colorClasses = {
    primary: "text-primary bg-primary/10 border-primary/20",
    success: "text-emerald-600 bg-emerald-50 border-emerald-200",
    warning: "text-amber-600 bg-amber-50 border-amber-200",
    danger: "text-red-600 bg-red-50 border-red-200",
  };

  return (
    <div className="rounded-xl glass p-4">
      <div className={cn("inline-flex p-2 rounded-lg border mb-2", colorClasses[color])}>
        {icon}
      </div>
      <p className="text-2xl font-bold font-mono text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
      {subValue && (
        <p className="text-[10px] text-muted-foreground/70 mt-0.5">{subValue}</p>
      )}
    </div>
  );
}

function FunctionHealthRow({ func }: { func: FunctionHealth }) {
  const getHealthColor = (score: number) => {
    if (score >= 80) return "text-emerald-600 bg-emerald-50 border-emerald-200";
    if (score >= 60) return "text-amber-600 bg-amber-50 border-amber-200";
    if (score >= 40) return "text-orange-600 bg-orange-50 border-orange-200";
    return "text-red-600 bg-red-50 border-red-200";
  };

  return (
    <div className="flex items-center gap-3 rounded-xl glass px-4 py-3 hover:bg-white/50 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-foreground truncate">{func.name}</p>
          {!func.hasDocstring && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200">
              No docstring
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate">{func.signature}</p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[10px] text-muted-foreground">
            {func.claimCount} claims
          </span>
          {func.violationCount > 0 && (
            <span className="text-[10px] text-red-600">
              {func.violationCount} violations
            </span>
          )}
          {func.categories.length > 0 && (
            <div className="flex gap-1">
              {func.categories.map((cat) => (
                <span
                  key={cat}
                  className="text-[9px] px-1 py-0.5 rounded text-white font-bold"
                  style={{ backgroundColor: CATEGORY_COLORS[cat as BCVCategory] }}
                >
                  {cat}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className={cn(
        "text-sm font-bold px-2.5 py-1 rounded-lg border",
        getHealthColor(func.healthScore)
      )}>
        {func.healthScore}
      </div>
    </div>
  );
}

function CoverageBar({ coverage }: { coverage: number }) {
  const getColor = (c: number) => {
    if (c >= 80) return "bg-emerald-500";
    if (c >= 60) return "bg-amber-500";
    if (c >= 40) return "bg-orange-500";
    return "bg-red-500";
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">Documentation Coverage</span>
        <span className="font-semibold text-foreground">{coverage}%</span>
      </div>
      <div className="h-3 rounded-full skeu-inset overflow-hidden">
        <div 
          className={cn("h-full rounded-full transition-all duration-500", getColor(coverage))}
          style={{ width: `${coverage}%` }}
        />
      </div>
    </div>
  );
}

export default function DocHealthPanel({ analysisId }: DocHealthPanelProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["doc-health", analysisId],
    queryFn: () => analysisApi.getDocHealth(analysisId).then((res) => res.data),
    enabled: !!analysisId,
  });

  if (isLoading) {
    return (
      <div className="rounded-2xl glass p-8 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl glass p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">Failed to load documentation health</p>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const { overallHealth, metrics, functions } = data;

  return (
    <div className="space-y-6">
      {/* Overall Health Score */}
      <div className="rounded-2xl glass p-6">
        <div className="flex items-center gap-6">
          <HealthGauge score={overallHealth} />
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-foreground mb-1">
              Documentation Health Score
            </h3>
            <p className="text-sm text-muted-foreground mb-3">
              Based on coverage, claim density, and violation rate
            </p>
            <CoverageBar coverage={metrics.coverage} />
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricCard
          icon={<FileText className="h-4 w-4" />}
          label="Documented"
          value={metrics.documentedFunctions}
          subValue={`of ${metrics.totalFunctions} functions`}
          color="success"
        />
        <MetricCard
          icon={<FileQuestion className="h-4 w-4" />}
          label="Undocumented"
          value={metrics.undocumentedFunctions}
          subValue="missing docstrings"
          color={metrics.undocumentedFunctions > 0 ? "warning" : "success"}
        />
        <MetricCard
          icon={<Layers className="h-4 w-4" />}
          label="Claim Density"
          value={metrics.claimDensity}
          subValue="claims per function"
          color="primary"
        />
        <MetricCard
          icon={<Activity className="h-4 w-4" />}
          label="Violation Rate"
          value={`${metrics.violationRate}%`}
          subValue={`${metrics.totalViolations} of ${metrics.totalClaims} claims`}
          color={metrics.violationRate > 20 ? "danger" : metrics.violationRate > 10 ? "warning" : "success"}
        />
      </div>

      {/* Function Health List */}
      {functions.length > 0 && (
        <div className="rounded-2xl glass overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-foreground/[0.06]">
            <TrendingUp className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground/80 uppercase tracking-wide">
              Function Health
            </h3>
            <span className="text-xs text-muted-foreground ml-auto">
              Sorted by health score (worst first)
            </span>
          </div>
          <div className="p-4 space-y-2 max-h-[400px] overflow-y-auto">
            {functions.map((func) => (
              <FunctionHealthRow key={func.id} func={func} />
            ))}
          </div>
        </div>
      )}

      {/* Health Tips */}
      <div className="rounded-2xl glass p-5">
        <h3 className="text-sm font-semibold text-foreground mb-3">Improvement Tips</h3>
        <div className="space-y-2">
          {metrics.undocumentedFunctions > 0 && (
            <div className="flex items-start gap-2 text-xs">
              <XCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
              <span className="text-muted-foreground">
                Add docstrings to {metrics.undocumentedFunctions} undocumented function{metrics.undocumentedFunctions > 1 ? "s" : ""} to improve coverage.
              </span>
            </div>
          )}
          {metrics.violationRate > 10 && (
            <div className="flex items-start gap-2 text-xs">
              <AlertTriangle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
              <span className="text-muted-foreground">
                {metrics.totalViolations} claims don't match actual behavior. Review and fix documentation or code.
              </span>
            </div>
          )}
          {metrics.claimDensity < 2 && (
            <div className="flex items-start gap-2 text-xs">
              <FileText className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
              <span className="text-muted-foreground">
                Consider adding more detailed documentation about parameters, return values, and exceptions.
              </span>
            </div>
          )}
          {overallHealth >= 80 && (
            <div className="flex items-start gap-2 text-xs">
              <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
              <span className="text-muted-foreground">
                Great job! Your documentation is in good health.
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
