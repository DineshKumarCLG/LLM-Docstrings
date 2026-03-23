import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Loader2, AlertCircle, Download, FileText } from "lucide-react";
import { useAnalysis, useViolationReport, useClaims } from "@/hooks/useAnalysis";
import CodeViewer from "@/components/code/CodeViewer";
import ExportDialog from "@/components/export/ExportDialog";
import { StaggerChildren, StaggerItem } from "@/components/ui";
import { CATEGORY_COLORS, type ClaimGroup } from "@/types";

export default function CodeViewerPage() {
  const { id } = useParams<{ id: string }>();
  const { data: analysis, isLoading, isError } = useAnalysis(id!);
  const { data: report } = useViolationReport(id!);
  const { data: claimGroups } = useClaims(id!) as { data: ClaimGroup[] | undefined };
  const [exportOpen, setExportOpen] = useState(false);

  if (isLoading) return <div className="flex h-screen items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;
  if (isError || !analysis) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12">
        <div className="flex items-center gap-2 rounded-2xl glass px-4 py-3 text-sm text-red-600"><AlertCircle className="h-4 w-4 shrink-0" /> Failed to load analysis.</div>
      </div>
    );
  }

  const sourceCode = (analysis as unknown as { sourceCode?: string }).sourceCode;
  const violations = report?.violations.filter((v) => v.outcome === "fail") ?? [];

  return (
    <div className="min-h-screen relative">
      <div className="fixed top-0 left-0 w-[600px] h-[600px] rounded-full bg-indigo-300/18 blur-[140px] pointer-events-none" />
      <header className="topbar sticky top-0 z-10">
        <div className="mx-auto max-w-5xl px-4 py-4 flex items-center justify-between">
          <Link to={`/analyses/${id}`} className="btn-tertiary"><ArrowLeft className="h-4 w-4" /> Back to analysis</Link>
          <button type="button" onClick={() => setExportOpen(true)} className="btn-secondary"><Download className="h-3.5 w-3.5" /> Export</button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-10 relative z-[1]">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24 }}
          className="mb-8"
        >
          <h1 className="text-2xl font-bold tracking-tight text-gradient-teal">{analysis.filename ?? "Pasted code"}</h1>
          <p className="mt-1 text-xs text-muted-foreground">Code view with inline violation annotations</p>
        </motion.div>

        {claimGroups && claimGroups.length > 0 && (
          <motion.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.06 }}
            className="mb-6"
          >
            <div className="flex items-center gap-2 mb-3">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Extracted Behavioral Claims</p>
            </div>
            <StaggerChildren className="space-y-3">
              {claimGroups.map((group) => (
                <StaggerItem key={group.functionName}>
                  <div className="rounded-2xl glass p-4">
                    <p className="mb-2 font-mono text-xs font-semibold text-foreground">{group.functionSignature}</p>
                    {group.docstring ? (
                      <div className="mb-3 rounded-xl skeu-inset p-3">
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Docstring</p>
                        <pre className="whitespace-pre-wrap font-mono text-xs text-foreground/70">{group.docstring}</pre>
                      </div>
                    ) : <p className="mb-3 text-xs italic text-muted-foreground">No docstring found.</p>}
                    {group.claims.length > 0 && (
                      <>
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Claims</p>
                        <ul className="space-y-1.5">
                          {group.claims.map((c) => (
                            <li key={c.id} className="flex items-start gap-2 text-xs">
                              <span className="mt-0.5 inline-flex shrink-0 items-center rounded-lg px-1.5 py-0.5 text-[10px] font-bold text-white" style={{ backgroundColor: CATEGORY_COLORS[c.category] }}>{c.category}</span>
                              <span className="text-muted-foreground">{c.rawText}{c.conditionality && <span className="ml-1 italic">({c.conditionality})</span>}<span className="ml-1 text-[10px] opacity-50">L{c.sourceLine}</span></span>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                </StaggerItem>
              ))}
            </StaggerChildren>
          </motion.section>
        )}

        {sourceCode ? <CodeViewer sourceCode={sourceCode} violations={violations} /> : (
          <div className="rounded-2xl glass border-dashed p-10 text-center text-sm text-muted-foreground">Source code not available for this analysis.</div>
        )}
      </main>
      <ExportDialog analysisId={id!} open={exportOpen} onOpenChange={setExportOpen} />
    </div>
  );
}
