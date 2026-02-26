/**
 * Code viewer page — displays Python source with inline violation annotations
 * and extracted behavioral claims (BCE output).
 *
 * Requirements: 8.7, 8.8
 */

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Loader2, AlertCircle, Download, FileText } from "lucide-react";
import { useAnalysis, useViolationReport, useClaims } from "@/hooks/useAnalysis";
import CodeViewer from "@/components/code/CodeViewer";
import ExportDialog from "@/components/export/ExportDialog";
import { CATEGORY_COLORS, type BCVCategory } from "@/types";

/** Shape returned by GET /api/analyses/{id}/claims */
interface ClaimGroup {
  functionName: string;
  functionSignature: string;
  docstring: string | null;
  source: string;
  lineno: number;
  claims: {
    id: string;
    category: BCVCategory;
    subject: string;
    predicateObject: string;
    conditionality: string | null;
    sourceLine: number;
    rawText: string;
  }[];
}

export default function CodeViewerPage() {
  const { id } = useParams<{ id: string }>();
  const { data: analysis, isLoading, isError } = useAnalysis(id!);
  const { data: report } = useViolationReport(id!);
  const { data: claimGroups } = useClaims(id!) as { data: ClaimGroup[] | undefined };
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
      <main className="mx-auto max-w-5xl px-4 py-12">
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load analysis.
        </div>
      </main>
    );
  }

  const sourceCode = (analysis as unknown as { sourceCode?: string }).sourceCode;
  const violations = report?.violations.filter((v) => v.outcome === "fail") ?? [];

  return (
    <main className="mx-auto max-w-5xl px-4 py-12">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <Link
            to={`/analyses/${id}`}
            className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to analysis
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">
            {analysis.filename ?? "Pasted code"} — Code View
          </h1>
        </div>
        <button
          type="button"
          onClick={() => setExportOpen(true)}
          className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm font-medium hover:bg-muted"
        >
          <Download className="h-4 w-4" />
          Export
        </button>
      </div>

      {/* Extracted Behavioral Claims (BCE output) */}
      {claimGroups && claimGroups.length > 0 && (
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-medium">Extracted Behavioral Claims</h2>
          </div>
          <div className="space-y-3">
            {claimGroups.map((group) => (
              <div key={group.functionName} className="rounded-lg border bg-card p-4">
                <p className="mb-1 font-mono text-xs font-medium">
                  {group.functionSignature}
                </p>
                {group.docstring ? (
                  <div className="mb-3 rounded-md bg-muted/50 p-3">
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Docstring
                    </p>
                    <pre className="whitespace-pre-wrap font-mono text-xs text-foreground/80">
                      {group.docstring}
                    </pre>
                  </div>
                ) : (
                  <p className="mb-3 text-xs italic text-muted-foreground">
                    No docstring found for this function.
                  </p>
                )}
                {group.claims.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No behavioral claims extracted.</p>
                ) : (
                  <>
                    <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Extracted Claims
                    </p>
                    <ul className="space-y-1.5">
                      {group.claims.map((c) => (
                        <li key={c.id} className="flex items-start gap-2 text-xs">
                          <span
                            className="mt-0.5 inline-flex shrink-0 items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold text-white"
                            style={{ backgroundColor: CATEGORY_COLORS[c.category] }}
                          >
                            {c.category}
                          </span>
                          <span className="text-muted-foreground">
                            {c.rawText}
                            {c.conditionality && (
                              <span className="ml-1 italic">({c.conditionality})</span>
                            )}
                            <span className="ml-1 text-[10px] opacity-60">
                              L{c.sourceLine}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Code viewer */}
      {sourceCode ? (
        <CodeViewer sourceCode={sourceCode} violations={violations} />
      ) : (
        <div className="rounded-lg border bg-muted/30 p-8 text-center text-sm text-muted-foreground">
          Source code not available for this analysis.
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
