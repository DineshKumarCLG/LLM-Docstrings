/**
 * Upload page — drag-and-drop .py file upload, code paste, LLM provider
 * selection, and Run Analysis trigger.
 *
 * Requirement 8.2
 */

import { useState, useCallback, useRef, type DragEvent, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, FileCode, X, Loader2, ChevronDown } from "lucide-react";
import { useCreateAnalysis } from "@/hooks/useAnalysis";
import { cn } from "@/lib/utils";
import type { LLMProvider } from "@/types";

const LLM_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: "gpt-4.1-mini", label: "GPT-4.1 Mini (OpenAI)" },
  { value: "claude-sonnet-4-20250514", label: "Claude Sonnet 4 (Anthropic)" },
  { value: "gemini-3-flash-preview", label: "Gemini 3 Flash (Google)" },
  { value: "bedrock", label: "Claude via Bedrock (AWS)" },
];

export default function FileUploader() {
  const navigate = useNavigate();
  const { mutate: createAnalysis, isPending, error } = useCreateAnalysis();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [sourceCode, setSourceCode] = useState("");
  const [llmProvider, setLlmProvider] = useState<LLMProvider>("gemini-3-flash-preview");
  const [dragOver, setDragOver] = useState(false);
  const [selectOpen, setSelectOpen] = useState(false);

  // ---- Input mode: file takes priority over paste ----
  const hasFile = file !== null;
  const hasCode = sourceCode.trim().length > 0;
  const canSubmit = (hasFile || hasCode) && !isPending;

  // ---- Drag-and-drop handlers ----
  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const onDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.name.endsWith(".py")) {
      setFile(dropped);
      setSourceCode("");
    }
  }, []);

  const onFileChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected && selected.name.endsWith(".py")) {
      setFile(selected);
      setSourceCode("");
    }
  }, []);

  const clearFile = useCallback(() => {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  // ---- Submit ----
  const handleSubmit = () => {
    if (!canSubmit) return;

    const formData = new FormData();
    if (hasFile) {
      formData.append("file", file!);
    } else {
      formData.append("source_code", sourceCode);
    }
    formData.append("llm_provider", llmProvider);

    createAnalysis(formData, {
      onSuccess: (data) => {
        navigate(`/analyses/${data.analysis_id}`);
      },
    });
  };

  // ---- Derived error message ----
  const errorMessage =
    error instanceof Error ? error.message : error ? String(error) : null;

  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight">Analyze Python Code</h1>
      <p className="mt-2 text-muted-foreground">
        Upload a <code>.py</code> file or paste your Python source code, then
        select an LLM provider to run the BCV detection pipeline.
      </p>

      {/* ---- Drag-and-drop zone ---- */}
      <div className="mt-8 space-y-6">
        <div>
          <label className="mb-2 block text-sm font-medium">Python File</label>
          <div
            role="button"
            tabIndex={0}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors",
              dragOver
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50 hover:bg-muted/50",
              hasFile && "border-primary/40 bg-primary/5",
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".py"
              className="hidden"
              onChange={onFileChange}
              aria-label="Upload Python file"
            />

            {hasFile ? (
              <div className="flex items-center gap-3">
                <FileCode className="h-6 w-6 text-primary" />
                <span className="text-sm font-medium">{file!.name}</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    clearFile();
                  }}
                  className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Remove file"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <>
                <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Drag &amp; drop a <code>.py</code> file here, or click to
                  browse
                </p>
              </>
            )}
          </div>
        </div>

        {/* ---- Divider ---- */}
        <div className="flex items-center gap-4">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs font-medium uppercase text-muted-foreground">
            or paste code
          </span>
          <div className="h-px flex-1 bg-border" />
        </div>

        {/* ---- Code paste textarea ---- */}
        <div>
          <label htmlFor="source-code" className="mb-2 block text-sm font-medium">
            Python Source Code
          </label>
          <textarea
            id="source-code"
            rows={10}
            value={sourceCode}
            onChange={(e) => {
              setSourceCode(e.target.value);
              if (e.target.value.trim()) setFile(null);
            }}
            disabled={hasFile}
            placeholder="# Paste your Python code here…"
            className={cn(
              "w-full rounded-lg border bg-background px-4 py-3 font-mono text-sm",
              "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring",
              "disabled:cursor-not-allowed disabled:opacity-50",
              "resize-y min-h-[120px]",
            )}
          />
        </div>

        {/* ---- LLM provider dropdown ---- */}
        <div>
          <label className="mb-2 block text-sm font-medium">LLM Provider</label>
          <div className="relative">
            <button
              type="button"
              onClick={() => setSelectOpen((o) => !o)}
              className={cn(
                "flex w-full items-center justify-between rounded-lg border bg-background px-4 py-2.5 text-sm",
                "focus:outline-none focus:ring-2 focus:ring-ring",
              )}
              aria-haspopup="listbox"
              aria-expanded={selectOpen}
            >
              <span>
                {LLM_OPTIONS.find((o) => o.value === llmProvider)?.label}
              </span>
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            </button>

            {selectOpen && (
              <ul
                role="listbox"
                className="absolute z-10 mt-1 w-full rounded-lg border bg-popover p-1 shadow-md"
              >
                {LLM_OPTIONS.map((opt) => (
                  <li
                    key={opt.value}
                    role="option"
                    aria-selected={opt.value === llmProvider}
                    onClick={() => {
                      setLlmProvider(opt.value);
                      setSelectOpen(false);
                    }}
                    className={cn(
                      "cursor-pointer rounded-md px-3 py-2 text-sm",
                      opt.value === llmProvider
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-muted",
                    )}
                  >
                    {opt.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* ---- Error message ---- */}
        {errorMessage && (
          <p className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {errorMessage}
          </p>
        )}

        {/* ---- Run Analysis button ---- */}
        <button
          type="button"
          disabled={!canSubmit}
          onClick={handleSubmit}
          className={cn(
            "inline-flex w-full items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-medium transition-colors",
            "bg-primary text-primary-foreground hover:bg-primary/90",
            "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
            "disabled:pointer-events-none disabled:opacity-50",
          )}
        >
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Submitting…
            </>
          ) : (
            <>
              <FileCode className="h-4 w-4" />
              Run Analysis
            </>
          )}
        </button>
      </div>
    </main>
  );
}
