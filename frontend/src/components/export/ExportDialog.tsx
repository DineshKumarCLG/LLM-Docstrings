import { useState } from "react";
import { motion } from "framer-motion";
import * as Dialog from "@radix-ui/react-dialog";
import { Download, X, FileJson, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { analysisApi } from "@/api/client";
import { ShimmerButton } from "@/components/ui";
import { cn } from "@/lib/utils";

interface ExportDialogProps { analysisId: string; open: boolean; onOpenChange: (open: boolean) => void; }

const FORMATS = [
  { value: "json", label: "JSON", icon: FileJson, desc: "Machine-readable" },
  { value: "csv",  label: "CSV",  icon: FileSpreadsheet, desc: "Spreadsheet" },
  { value: "pdf",  label: "PDF",  icon: FileText, desc: "Printable report" },
] as const;
type ExportFormat = (typeof FORMATS)[number]["value"];

export default function ExportDialog({ analysisId, open, onOpenChange }: ExportDialogProps) {
  const [selected, setSelected] = useState<ExportFormat>("json");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloading(true); setError(null);
    try {
      const { data } = await analysisApi.export(analysisId, selected);
      const blob = data instanceof Blob ? data : new Blob([data]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `veridoc-report-${analysisId.slice(0, 8)}.${selected}`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      onOpenChange(false);
    } catch { setError("Download failed. Please try again."); }
    finally { setDownloading(false); }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-3xl glass-strong p-6 shadow-[0_8px_32px_rgba(0,0,0,0.12),0_32px_80px_rgba(0,0,0,0.16)] focus:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="mb-1 flex items-center justify-between">
            <Dialog.Title className="text-base font-semibold">Export Report</Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" className="rounded-lg p-1.5 text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground transition-colors" aria-label="Close"><X className="h-4 w-4" /></button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="mb-5 text-xs text-muted-foreground">Choose a format to download the violation report.</Dialog.Description>

          <div className="mb-5 grid grid-cols-3 gap-2">
            {FORMATS.map((fmt, idx) => {
              const Icon = fmt.icon;
              const isSelected = selected === fmt.value;
              return (
                <motion.button
                  key={fmt.value}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 260, damping: 24, delay: idx * 0.05 }}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  type="button"
                  onClick={() => setSelected(fmt.value)}
                  className={cn("flex flex-col items-center gap-2 rounded-2xl p-4 text-sm font-medium transition-all duration-200",
                    isSelected ? "glass-strong border-indigo-300/50 text-foreground glow-primary" : "glass text-muted-foreground hover:text-foreground",
                  )}>
                  <Icon className="h-5 w-5" />
                  <span>{fmt.label}</span>
                  <span className="text-[10px] font-normal opacity-50">{fmt.desc}</span>
                </motion.button>
              );
            })}
          </div>

          {error && <p className="mb-4 text-xs text-red-600">{error}</p>}

          <ShimmerButton onClick={handleDownload} disabled={downloading} className="w-full">
            {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {downloading ? "Downloading…" : "Download"}
          </ShimmerButton>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
