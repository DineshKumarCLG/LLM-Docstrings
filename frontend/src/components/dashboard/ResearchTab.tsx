import { BookOpen, FlaskConical, BarChart3, Lightbulb, ArrowRight, Database, Cpu, TestTube2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { StaggerChildren, StaggerItem } from "@/components/ui";
import { BCV_TAXONOMY, PYBCV_420_STATS, PIPELINE_STAGES } from "@/lib/constants";
import { CATEGORY_COLORS } from "@/types";

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

function PaperAbstract() {
  return (
    <Section icon={<BookOpen className="h-4 w-4 text-blue-600" />} title="Paper Abstract">
      <p className="text-sm leading-relaxed text-muted-foreground">
        Large Language Models (LLMs) frequently generate plausible-sounding but incorrect documentation for code — a phenomenon we term{" "}
        <span className="font-semibold text-foreground">docstring hallucination</span>. VeriDoc introduces{" "}
        <span className="font-semibold text-foreground">Behavioral Contract Verification (BCV)</span>, a three-stage pipeline that automatically detects mismatches between function documentation and actual runtime behavior. The pipeline extracts behavioral claims from docstrings, synthesizes differential property-based tests, and executes them against the implementation to surface violations. We define a six-category taxonomy of Behavioral Contract Violations (BCVs) and present{" "}
        <span className="font-semibold text-foreground">PyBCV-420</span>, a benchmark of 420 Python functions with seeded documentation hallucinations across all six categories.
      </p>
    </Section>
  );
}

function ArchitectureDiagram() {
  return (
    <Section icon={<Cpu className="h-4 w-4 text-purple-600" />} title="System Architecture">
      <p className="mb-4 text-xs text-muted-foreground">The BCV pipeline processes source code through three sequential stages to detect docstring hallucinations.</p>
      <div className="flex flex-col items-center gap-3 sm:flex-row sm:gap-0 sm:justify-center">
        {PIPELINE_STAGES.map((stage, idx) => (
          <div key={stage.key} className="flex items-center gap-3">
            <div className={cn("relative flex flex-col items-center rounded-2xl p-4 text-center w-48 glass")}>
              <div className={cn("mb-2 flex h-10 w-10 items-center justify-center rounded-xl border",
                idx === 0 && "text-indigo-600 bg-indigo-500/10 border-indigo-500/20",
                idx === 1 && "text-emerald-600 bg-emerald-500/10 border-emerald-500/20",
                idx === 2 && "text-amber-600 bg-amber-500/10 border-amber-500/20",
              )}>
                {idx === 0 && <Database className="h-5 w-5" />}
                {idx === 1 && <FlaskConical className="h-5 w-5" />}
                {idx === 2 && <TestTube2 className="h-5 w-5" />}
              </div>
              <span className="text-xs font-bold text-foreground uppercase tracking-wider">{stage.label}</span>
              <span className="mt-0.5 text-[11px] font-medium text-foreground/80">{stage.fullName}</span>
              <span className="mt-1 text-[10px] text-muted-foreground leading-snug">{stage.description}</span>
            </div>
            {idx < PIPELINE_STAGES.length - 1 && <ArrowRight className="hidden sm:block h-5 w-5 text-foreground/20 shrink-0" />}
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-xl skeu-inset px-4 py-2">
        <p className="text-[11px] text-muted-foreground text-center">
          <span className="font-medium text-foreground">Source Code + Docstrings</span>{" → "}
          <span className="text-indigo-600">Behavioral Claims</span>{" → "}
          <span className="text-emerald-600">Property-Based Tests</span>{" → "}
          <span className="text-amber-600">Violation Report</span>
        </p>
      </div>
    </Section>
  );
}

function FullTaxonomyTable() {
  return (
    <Section icon={<FlaskConical className="h-4 w-4 text-emerald-600" />} title="BCV Taxonomy">
      <p className="mb-4 text-xs text-muted-foreground">Six categories of Behavioral Contract Violations, each with a hallucination example and the expected correct behavior.</p>
      <div className="space-y-3">
        {BCV_TAXONOMY.map((entry) => {
          const color = CATEGORY_COLORS[entry.category];
          return (
            <div key={entry.category} className="rounded-xl glass overflow-hidden" style={{ borderLeftWidth: 4, borderLeftColor: color }}>
              <div className="flex items-center gap-3 px-4 py-2.5 border-b border-foreground/[0.04]">
                <span className="inline-flex items-center justify-center rounded-lg px-2 py-0.5 text-xs font-bold text-white" style={{ backgroundColor: color }}>{entry.category}</span>
                <span className="text-sm font-semibold text-foreground/90">{entry.fullName}</span>
              </div>
              <div className="px-4 py-3 space-y-2">
                <p className="text-xs text-muted-foreground leading-relaxed">{entry.description}</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg bg-red-500/5 border border-red-500/10 px-3 py-2">
                    <p className="text-[10px] font-semibold text-red-600 uppercase tracking-wide mb-0.5">Hallucination Example</p>
                    <p className="text-xs text-muted-foreground leading-relaxed">{entry.hallucinationExample}</p>
                  </div>
                  <div className="rounded-lg bg-emerald-500/5 border border-emerald-500/10 px-3 py-2">
                    <p className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wide mb-0.5">Correct Behavior</p>
                    <p className="text-xs text-muted-foreground leading-relaxed">{entry.correctBehavior}</p>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function BenchmarkStatsSection() {
  const stats = PYBCV_420_STATS;
  return (
    <Section icon={<BarChart3 className="h-4 w-4 text-amber-600" />} title="PyBCV-420 Benchmark">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-4">
        {[
          { label: "Total Instances", value: stats.totalInstances },
          { label: "Categories", value: stats.categories },
          { label: "LLMs Tested", value: stats.llmsTested },
          { label: "Per Category", value: stats.totalInstances / stats.categories },
        ].map((s) => (
          <div key={s.label} className="rounded-xl skeu-raised px-3 py-2.5 text-center">
            <p className="text-2xl font-bold font-mono text-foreground leading-none">{s.value}</p>
            <p className="mt-1 text-[10px] text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>
      <div className="mb-4">
        <p className="text-xs font-medium text-foreground mb-2">Category Distribution</p>
        <div className="flex flex-wrap gap-2">
          {(Object.entries(stats.categoryDistribution) as [string, number][]).map(([cat, count]) => {
            const color = CATEGORY_COLORS[cat as keyof typeof CATEGORY_COLORS];
            return (
              <span key={cat} className="inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs" style={{ borderColor: `${color}40`, color, backgroundColor: `${color}10` }}>
                <span className="font-bold">{cat}</span>
                <span className="text-muted-foreground">×{count}</span>
              </span>
            );
          })}
        </div>
      </div>
      <div>
        <p className="text-xs font-medium text-foreground mb-2">LLM Self-Detection Rates</p>
        <div className="space-y-2">
          {stats.llmNames.map((name) => {
            const rate = stats.detectionRates[name] ?? 0;
            return (
              <div key={name} className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground w-36 shrink-0 truncate">{name}</span>
                <div className="flex-1 h-2 rounded-full skeu-inset overflow-hidden">
                  <div className="h-full rounded-full bg-red-500 transition-all duration-300" style={{ width: `${Math.max(rate * 100, 1)}%` }} />
                </div>
                <span className="text-xs font-mono text-muted-foreground w-12 text-right">{(rate * 100).toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground italic">All tested LLMs achieved 0% self-detection rate.</p>
      </div>
    </Section>
  );
}

const KEY_FINDINGS = [
  { title: "LLMs Cannot Self-Detect Docstring Hallucinations", description: "All three tested LLMs achieved a 0% detection rate when asked to identify documentation-code mismatches in their own generated docstrings." },
  { title: "BCV Pipeline Achieves Automated Detection", description: "The three-stage BCV pipeline reliably detects behavioral contract violations that LLMs miss, using property-based testing as the verification mechanism." },
  { title: "Six Distinct Violation Categories Identified", description: "The BCV taxonomy covers return specifications, parameter contracts, side effects, exception contracts, completeness omissions, and complexity contracts." },
  { title: "PyBCV-420 Enables Reproducible Evaluation", description: "The benchmark contains 420 Python functions with carefully seeded hallucinations, enabling standardized evaluation of documentation verification tools." },
  { title: "Runtime Verification Outperforms Static Analysis", description: "By executing synthesized property-based tests against actual implementations, the pipeline detects behavioral mismatches that static analysis cannot identify." },
];

function KeyFindings() {
  return (
    <Section icon={<Lightbulb className="h-4 w-4 text-yellow-600" />} title="Key Research Findings">
      <div className="space-y-3">
        {KEY_FINDINGS.map((finding, idx) => (
          <div key={idx} className="flex gap-3 rounded-xl glass px-4 py-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-yellow-500/10 border border-yellow-500/20 text-[10px] font-bold text-yellow-600">{idx + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-foreground/90 leading-snug">{finding.title}</p>
              <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">{finding.description}</p>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

export default function ResearchTab() {
  return (
    <StaggerChildren className="space-y-6">
      <StaggerItem><PaperAbstract /></StaggerItem>
      <StaggerItem><ArchitectureDiagram /></StaggerItem>
      <StaggerItem><FullTaxonomyTable /></StaggerItem>
      <StaggerItem><BenchmarkStatsSection /></StaggerItem>
      <StaggerItem><KeyFindings /></StaggerItem>
    </StaggerChildren>
  );
}
