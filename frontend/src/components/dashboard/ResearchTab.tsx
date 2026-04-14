import { useQuery } from "@tanstack/react-query";
import { 
  BarChart3, 
  TrendingUp, 
  FileCode, 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  Layers,
  Code2,
  Activity,
  Zap
} from "lucide-react";
import { cn } from "@/lib/utils";
import { StaggerChildren, StaggerItem } from "@/components/ui";
import { analysisApi } from "@/api/client";
import { CATEGORY_COLORS, CATEGORY_LABELS, type BCVCategory, type Stats } from "@/types";

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl glass overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-foreground/[0.06]">
        {icon}
        <h2 className="text-sm font-semibold text-foreground/80 uppercase tracking-wide">{title}</h2>
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

function StatCard({ label, value, icon, trend }: { label: string; value: string | number; icon: React.ReactNode; trend?: string }) {
  return (
    <div className="rounded-xl skeu-raised px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-muted-foreground">{icon}</span>
        {trend && (
          <span className="text-xs text-emerald-600 font-medium">{trend}</span>
        )}
      </div>
      <p className="text-2xl font-bold font-mono text-foreground leading-none">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function OverviewStats({ stats }: { stats: Stats }) {
  return (
    <Section icon={<Activity className="h-4 w-4 text-primary" />} title="Overview">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard 
          label="Total Analyses" 
          value={stats.totalAnalyses} 
          icon={<FileCode className="h-4 w-4" />}
        />
        <StatCard 
          label="Completed" 
          value={stats.completedAnalyses} 
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <StatCard 
          label="Functions Analyzed" 
          value={stats.totalFunctions} 
          icon={<Code2 className="h-4 w-4" />}
        />
        <StatCard 
          label="Claims Extracted" 
          value={stats.totalClaims} 
          icon={<Layers className="h-4 w-4" />}
        />
        <StatCard 
          label="Violations Found" 
          value={stats.totalViolations} 
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <StatCard 
          label="Avg BCV Rate" 
          value={`${(stats.avgBcvRate * 100).toFixed(1)}%`} 
          icon={<TrendingUp className="h-4 w-4" />}
        />
      </div>
    </Section>
  );
}

function CategoryBreakdown({ breakdown }: { breakdown: Record<string, number> }) {
  const categories = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);
  const total = categories.reduce((sum, [, count]) => sum + count, 0);

  if (total === 0) {
    return (
      <Section icon={<BarChart3 className="h-4 w-4 text-amber-600" />} title="Violations by Category">
        <p className="text-sm text-muted-foreground text-center py-8">
          No violations detected yet. Run some analyses to see category breakdown.
        </p>
      </Section>
    );
  }

  return (
    <Section icon={<BarChart3 className="h-4 w-4 text-amber-600" />} title="Violations by Category">
      <div className="space-y-3">
        {categories.map(([cat, count]) => {
          const color = CATEGORY_COLORS[cat as BCVCategory] || "#64748b";
          const label = CATEGORY_LABELS[cat as BCVCategory] || cat;
          const percentage = total > 0 ? (count / total) * 100 : 0;
          return (
            <div key={cat} className="flex items-center gap-3">
              <span 
                className="inline-flex items-center justify-center rounded-lg px-2 py-0.5 text-xs font-bold text-white w-12"
                style={{ backgroundColor: color }}
              >
                {cat}
              </span>
              <span className="text-xs text-muted-foreground w-32 truncate">{label}</span>
              <div className="flex-1 h-2 rounded-full skeu-inset overflow-hidden">
                <div 
                  className="h-full rounded-full transition-all duration-500" 
                  style={{ width: `${percentage}%`, backgroundColor: color }} 
                />
              </div>
              <span className="text-xs font-mono text-muted-foreground w-16 text-right">
                {count} ({percentage.toFixed(0)}%)
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {categories.map(([cat, count]) => {
          const color = CATEGORY_COLORS[cat as BCVCategory] || "#64748b";
          return (
            <span 
              key={cat}
              className="inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs"
              style={{ borderColor: `${color}40`, color, backgroundColor: `${color}10` }}
            >
              <span className="font-bold">{cat}</span>
              <span className="text-muted-foreground">×{count}</span>
            </span>
          );
        })}
      </div>
    </Section>
  );
}

function LanguageDistribution({ distribution }: { distribution: Record<string, number> }) {
  const languages = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const total = languages.reduce((sum, [, count]) => sum + count, 0);

  const langColors: Record<string, string> = {
    python: "#3572A5",
    javascript: "#f1e05a",
    typescript: "#3178c6",
    java: "#b07219",
    go: "#00ADD8",
    rust: "#dea584",
  };

  if (total === 0) {
    return (
      <Section icon={<Code2 className="h-4 w-4 text-blue-600" />} title="Language Distribution">
        <p className="text-sm text-muted-foreground text-center py-8">
          No analyses yet. Upload some code to see language distribution.
        </p>
      </Section>
    );
  }

  return (
    <Section icon={<Code2 className="h-4 w-4 text-blue-600" />} title="Language Distribution">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {languages.map(([lang, count]) => {
          const color = langColors[lang] || "#64748b";
          const percentage = total > 0 ? (count / total) * 100 : 0;
          return (
            <div key={lang} className="rounded-xl glass px-4 py-3" style={{ borderLeftWidth: 3, borderLeftColor: color }}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold capitalize text-foreground">{lang}</span>
                <span className="text-xs font-mono text-muted-foreground">{percentage.toFixed(0)}%</span>
              </div>
              <p className="text-2xl font-bold font-mono text-foreground mt-1">{count}</p>
              <p className="text-xs text-muted-foreground">analyses</p>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function ProviderStats({ usage, rates }: { usage: Record<string, number>; rates: Record<string, number> }) {
  const providers = Object.keys(usage);

  const providerLabels: Record<string, string> = {
    "gpt-4.1-mini": "GPT-4.1 Mini",
    "claude-sonnet-4-20250514": "Claude Sonnet 4",
    "gemma-4-31b-it": "Gemma 4 31B",
    "bedrock": "AWS Bedrock",
  };

  if (providers.length === 0) {
    return (
      <Section icon={<Zap className="h-4 w-4 text-purple-600" />} title="LLM Provider Performance">
        <p className="text-sm text-muted-foreground text-center py-8">
          No completed analyses yet. Run some analyses to see provider performance.
        </p>
      </Section>
    );
  }

  return (
    <Section icon={<Zap className="h-4 w-4 text-purple-600" />} title="LLM Provider Performance">
      <div className="space-y-4">
        {providers.map((provider) => {
          const count = usage[provider] || 0;
          const rate = rates[provider] || 0;
          const label = providerLabels[provider] || provider;
          return (
            <div key={provider} className="rounded-xl glass px-4 py-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-foreground">{label}</span>
                <span className="text-xs text-muted-foreground">{count} analyses</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground w-24">Detection Rate</span>
                <div className="flex-1 h-2 rounded-full skeu-inset overflow-hidden">
                  <div 
                    className="h-full rounded-full bg-primary transition-all duration-500" 
                    style={{ width: `${Math.max(rate * 100, 1)}%` }} 
                  />
                </div>
                <span className="text-xs font-mono text-foreground w-14 text-right font-semibold">
                  {(rate * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-[10px] text-muted-foreground italic">
        Detection rate = violations found ÷ total claims extracted
      </p>
    </Section>
  );
}

function RecentAnalyses({ analyses }: { analyses: Stats["recentAnalyses"] }) {
  if (analyses.length === 0) {
    return (
      <Section icon={<Clock className="h-4 w-4 text-slate-600" />} title="Recent Analyses">
        <p className="text-sm text-muted-foreground text-center py-8">
          No analyses yet. Upload some code to get started.
        </p>
      </Section>
    );
  }

  const statusColors: Record<string, string> = {
    complete: "text-emerald-600 bg-emerald-50 border-emerald-200",
    failed: "text-red-600 bg-red-50 border-red-200",
    pending: "text-amber-600 bg-amber-50 border-amber-200",
  };

  return (
    <Section icon={<Clock className="h-4 w-4 text-slate-600" />} title="Recent Analyses">
      <div className="space-y-2">
        {analyses.map((analysis) => {
          const statusClass = analysis.status === "complete" 
            ? statusColors.complete 
            : analysis.status === "failed" 
              ? statusColors.failed 
              : statusColors.pending;
          return (
            <div key={analysis.id} className="flex items-center gap-3 rounded-xl glass px-4 py-2.5">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">
                  {analysis.filename || "Code paste"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {analysis.language} • {analysis.totalClaims} claims • {analysis.totalViolations} violations
                </p>
              </div>
              <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full border", statusClass)}>
                {analysis.status}
              </span>
              {analysis.status === "complete" && (
                <span className="text-xs font-mono text-muted-foreground">
                  {(analysis.bcvRate * 100).toFixed(0)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl glass p-12 text-center">
      <BarChart3 className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
      <h3 className="text-lg font-semibold text-foreground mb-2">No Data Yet</h3>
      <p className="text-sm text-muted-foreground max-w-md mx-auto">
        Upload and analyze some code to see statistics here. The Research tab shows aggregate metrics 
        across all your analyses including violation categories, language distribution, and LLM performance.
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      {[1, 2, 3].map((i) => (
        <div key={i} className="rounded-2xl glass p-6 animate-pulse">
          <div className="h-4 bg-muted rounded w-1/4 mb-4" />
          <div className="grid grid-cols-3 gap-4">
            <div className="h-20 bg-muted rounded" />
            <div className="h-20 bg-muted rounded" />
            <div className="h-20 bg-muted rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ResearchTab() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ["stats"],
    queryFn: () => analysisApi.getStats().then((res) => res.data),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  if (isLoading) {
    return <LoadingState />;
  }

  if (error) {
    return (
      <div className="rounded-2xl glass p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-3" />
        <p className="text-sm text-muted-foreground">Failed to load statistics</p>
      </div>
    );
  }

  if (!stats || stats.totalAnalyses === 0) {
    return <EmptyState />;
  }

  return (
    <StaggerChildren className="space-y-6">
      <StaggerItem><OverviewStats stats={stats} /></StaggerItem>
      <div className="grid gap-6 lg:grid-cols-2">
        <StaggerItem><CategoryBreakdown breakdown={stats.categoryBreakdown} /></StaggerItem>
        <StaggerItem><LanguageDistribution distribution={stats.languageDistribution} /></StaggerItem>
      </div>
      <StaggerItem><ProviderStats usage={stats.providerUsage} rates={stats.detectionRates} /></StaggerItem>
      <StaggerItem><RecentAnalyses analyses={stats.recentAnalyses} /></StaggerItem>
    </StaggerChildren>
  );
}
