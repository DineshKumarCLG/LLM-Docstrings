/**
 * Export dialog — format selection (JSON, CSV, PDF) with download trigger.
 *
 * Uses @radix-ui/react-dialog for the modal and analysisApi.export()
 * to fetch the blob and trigger a browser download.
 *
 * Requirements: 8.8
 */

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Download, X, FileJson, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { analysisApi } from "@/api/client";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ExportDialogProps {
  analysisId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Format options
// ---------------------------------------------------------------------------

const FORMATS = [
  { value: "json", label: "JSON", icon: FileJson, ext: "json", mime: "application/json" },
  { value: "csv", label: "CSV", icon: FileSpreadsheet, ext: "csv", mime: "text/csv" },
  { value: "pdf", label: "PDF", icon: FileText, ext: "pdf", mime: "application/pdf" },
] as const;

type ExportFormat = (typeof FORMATS)[number]["value"];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ExportDialog({
  analysisId,
  open,
  onOpenChange,
}: ExportDialogProps) {
  const [selected, setSelected] = useState<ExportFormat>("json");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      const { data } = await analysisApi.export(analysisId, selected);
      const blob = data instanceof Blob ? data : new Blob([data]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `veridoc-report-${analysisId.slice(0, 8)}.${selected}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      onOpenChange(false);
    } catch {
      setError("Download failed. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-card p-6 shadow-lg focus:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">
              Export Report
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <Dialog.Description className="mb-4 text-sm text-muted-foreground">
            Choose a format to download the violation report.
          </Dialog.Description>

          {/* Format selection */}
          <div className="mb-6 grid grid-cols-3 gap-3">
            {FORMATS.map((fmt) => {
              const Icon = fmt.icon;
              const isSelected = selected === fmt.value;
              return (
                <button
                  key={fmt.value}
                  type="button"
                  onClick={() => setSelected(fmt.value)}
                  className={
                    isSelected
                      ? "flex flex-col items-center gap-2 rounded-lg border-2 border-primary bg-primary/5 p-4 text-sm font-medium"
                      : "flex flex-col items-center gap-2 rounded-lg border-2 border-transparent bg-muted/40 p-4 text-sm font-medium text-muted-foreground hover:border-border hover:text-foreground"
                  }
                >
                  <Icon className="h-6 w-6" />
                  {fmt.label}
                </button>
              );
            })}
          </div>

          {error && (
            <p className="mb-4 text-sm text-destructive">{error}</p>
          )}

          {/* Download button */}
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {downloading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {downloading ? "Downloading…" : "Download"}
          </button>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
