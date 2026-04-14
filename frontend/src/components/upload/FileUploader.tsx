import { useState, useCallback, useRef, type DragEvent, type ChangeEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Upload, FileCode, FolderArchive, FolderOpen, X, Loader2, ArrowLeft, Activity, Layers } from "lucide-react";
import { useCreateAnalysis, useCreateBatchAnalysis, useCreateBatchFromFolder } from "@/hooks/useAnalysis";
import { ShimmerButton } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { LLMProvider, SupportedLanguage, FileWithPath } from "@/types";
import FolderPicker from "./FolderPicker";

const LLM_OPTIONS: { value: LLMProvider; label: string; badge?: string }[] = [
  { value: "gemma-4-31b-it",   label: "Gemma 4 31B",  badge: "Recommended" },
  { value: "gpt-4.1-mini",             label: "GPT-4.1 Mini" },
  { value: "claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
  { value: "bedrock",                  label: "Claude via Bedrock" },
];

const SUPPORTED_EXTENSIONS: Record<string, SupportedLanguage> = {
  ".py": "python", ".js": "javascript", ".jsx": "javascript",
  ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".go": "go", ".rs": "rust",
};
const ACCEPTED_FILE_EXTENSIONS = ".py,.js,.jsx,.ts,.tsx,.java,.go,.rs";
const LANGUAGE_LABELS: Record<SupportedLanguage, { label: string; color: string }> = {
  python: { label: "Python", color: "text-blue-600" }, javascript: { label: "JavaScript", color: "text-yellow-600" },
  typescript: { label: "TypeScript", color: "text-blue-500" }, java: { label: "Java", color: "text-orange-600" },
  go: { label: "Go", color: "text-cyan-600" }, rust: { label: "Rust", color: "text-red-600" },
};
type UploadMode = "file" | "project" | "folder";

function detectLanguage(filename: string): SupportedLanguage | null {
  const idx = filename.lastIndexOf(".");
  if (idx === -1) return null;
  return SUPPORTED_EXTENSIONS[filename.slice(idx).toLowerCase()] ?? null;
}
function isSupportedFile(file: File): boolean { return detectLanguage(file.name) !== null; }

export default function FileUploader() {
  const navigate = useNavigate();
  const { mutate: createAnalysis, isPending: isPendingSingle, error: errorSingle } = useCreateAnalysis();
  const { mutate: createBatch, isPending: isPendingBatch, error: errorBatch } = useCreateBatchAnalysis();
  const { mutate: createBatchFromFolder, isPending: isPendingFolder, error: errorFolder } = useCreateBatchFromFolder();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<UploadMode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [sourceCode, setSourceCode] = useState("");
  const [llmProvider, setLlmProvider] = useState<LLMProvider>("gemma-4-31b-it");
  const [dragOver, setDragOver] = useState(false);
  const [folderFiles, setFolderFiles] = useState<FileWithPath[]>([]);

  const isPending = isPendingSingle || isPendingBatch || isPendingFolder;
  const error = errorSingle || errorBatch || errorFolder;
  const isZip = file?.name.endsWith(".zip") ?? false;
  const hasFile = file !== null;
  const hasCode = sourceCode.trim().length > 0;
  const hasFolderFiles = folderFiles.length > 0;
  const canSubmit = ((hasFile || (mode === "file" && hasCode)) || (mode === "folder" && hasFolderFiles)) && !isPending;
  const acceptedTypes = mode === "project" ? ".zip" : ACCEPTED_FILE_EXTENSIONS;
  const detectedLanguage = file ? detectLanguage(file.name) : null;

  const validateAndSetFile = useCallback((f: File) => {
    if (mode === "project" && f.name.endsWith(".zip")) { setFile(f); setSourceCode(""); }
    else if (mode === "file" && isSupportedFile(f)) { setFile(f); setSourceCode(""); }
  }, [mode]);

  const onDragOver = useCallback((e: DragEvent) => { e.preventDefault(); setDragOver(true); }, []);
  const onDragLeave = useCallback((e: DragEvent) => { e.preventDefault(); setDragOver(false); }, []);
  const onDrop = useCallback((e: DragEvent) => { e.preventDefault(); setDragOver(false); const d = e.dataTransfer.files[0]; if (d) validateAndSetFile(d); }, [validateAndSetFile]);
  const onFileChange = useCallback((e: ChangeEvent<HTMLInputElement>) => { const s = e.target.files?.[0]; if (s) validateAndSetFile(s); }, [validateAndSetFile]);
  const clearFile = useCallback(() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }, []);
  const handleFolderFilesSelected = useCallback((files: FileWithPath[]) => { setFolderFiles(files); }, []);

  const switchMode = (m: UploadMode) => {
    setMode(m); setFile(null); setSourceCode(""); setFolderFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = () => {
    if (!canSubmit) return;
    const formData = new FormData();
    formData.append("llm_provider", llmProvider);
    if (mode === "project" && hasFile) {
      formData.append("file", file!);
      createBatch(formData, { onSuccess: (data) => navigate(`/batches/${data.batch_id}`) });
    } else if (mode === "folder" && hasFolderFiles) {
      createBatchFromFolder({ files: folderFiles, llmProvider }, { onSuccess: (data) => navigate(`/batches/${data.batch_id}`) });
    } else {
      if (hasFile) formData.append("file", file!);
      else formData.append("source_code", sourceCode);
      createAnalysis(formData, { onSuccess: (data) => navigate(`/analyses/${data.analysis_id}`) });
    }
  };

  const errorMessage = error instanceof Error ? error.message : error ? String(error) : null;
  const submitLabel = mode === "project" ? "Analyse Project" : mode === "folder" ? "Analyse Folder" : "Run Analysis";
  const pendingLabel = mode === "project" ? "Uploading project…" : mode === "folder" ? "Uploading folder…" : "Submitting…";

  return (
    <div className="min-h-screen relative">
      <div className="fixed top-20 right-10 w-[500px] h-[500px] rounded-full bg-indigo-300/20 blur-[120px] pointer-events-none" />
      <div className="fixed bottom-20 left-10 w-[400px] h-[400px] rounded-full bg-violet-300/18 blur-[120px] pointer-events-none" />
      <div className="fixed top-[60%] right-[40%] w-[250px] h-[250px] rounded-full bg-blue-200/12 blur-[80px] pointer-events-none" />

      <header className="topbar sticky top-0 z-10">
        <div className="mx-auto max-w-2xl px-4 py-4 flex items-center gap-3">
          <Link to="/" className="btn-tertiary"><ArrowLeft className="h-4 w-4" /> Back</Link>
          <span className="text-foreground/10">·</span>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl skeu-raised"><Activity className="h-4 w-4 text-indigo-500" /></div>
            <span className="text-sm font-bold">VeriDoc</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-4 py-12 relative z-[1]">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24 }}
          className="mb-10"
        >
          <h1 className="text-3xl font-extrabold tracking-tight text-gradient-teal">Analyze Source Code</h1>
          <p className="mt-3 text-sm text-muted-foreground">Upload a single file, a project ZIP, or select a folder. Supports Python, JavaScript, TypeScript, Java, Go, and Rust.</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.06 }}
          className="space-y-6"
        >
          <div className="flex items-center gap-1 rounded-2xl skeu-inset p-1.5 w-fit">
            {([
              { key: "file" as UploadMode, icon: FileCode, label: "File" },
              { key: "project" as UploadMode, icon: FolderArchive, label: "Project" },
              { key: "folder" as UploadMode, icon: FolderOpen, label: "Folder" },
            ]).map(({ key, icon: Icon, label }) => (
              <button key={key} type="button" onClick={() => switchMode(key)}
                className={cn("flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all duration-200",
                  mode === key ? "glass-strong text-indigo-600 shadow-[0_2px_8px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)]" : "text-muted-foreground hover:text-foreground hover:bg-white/40",
                )}>
                <Icon className="h-4 w-4" /> {label}
              </button>
            ))}
          </div>

          {mode === "folder" && (
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground/80">Project Folder</label>
              <FolderPicker onFilesSelected={handleFolderFilesSelected} />
            </div>
          )}

          {mode !== "folder" && (
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground/80">{mode === "project" ? "Project ZIP Archive" : "Source File"}</label>
              <div role="button" tabIndex={0} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click(); }}
                className={cn(
                  "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-12 transition-all duration-300",
                  dragOver && "border-indigo-400 bg-indigo-50/60 scale-[1.02] shadow-[0_0_48px_rgba(99,102,241,0.12),0_0_0_1px_rgba(99,102,241,0.15)]",
                  !dragOver && !hasFile && "border-foreground/[0.08] hover:border-indigo-400/40 hover:bg-white/40 hover:shadow-[0_8px_32px_rgba(0,0,0,0.06),inset_0_1px_0_rgba(255,255,255,0.80)]",
                  hasFile && "border-indigo-400/30 bg-indigo-50/40 shadow-[0_0_32px_rgba(99,102,241,0.08),inset_0_1px_0_rgba(255,255,255,0.70)]",
                )}>
                <input ref={fileInputRef} type="file" accept={acceptedTypes} className="hidden" onChange={onFileChange} aria-label={mode === "project" ? "Upload ZIP archive" : "Upload source file"} />
                {hasFile ? (
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl skeu-raised">
                      {isZip ? <FolderArchive className="h-5 w-5 text-indigo-500" /> : <FileCode className="h-5 w-5 text-indigo-500" />}
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{file!.name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <p className="text-xs text-muted-foreground">{(file!.size / 1024).toFixed(1)} KB</p>
                        {detectedLanguage && <span className={cn("text-xs font-bold", LANGUAGE_LABELS[detectedLanguage].color)}>{LANGUAGE_LABELS[detectedLanguage].label}</span>}
                      </div>
                    </div>
                    <button type="button" onClick={(e) => { e.stopPropagation(); clearFile(); }} className="ml-2 rounded-xl p-2 text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground transition-all" aria-label="Remove file"><X className="h-4 w-4" /></button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3 text-center">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl skeu-raised">
                      {mode === "project" ? <FolderArchive className="h-6 w-6 text-muted-foreground" /> : <Upload className="h-6 w-6 text-muted-foreground" />}
                    </div>
                    <p className="text-sm text-muted-foreground">{mode === "project" ? <>Drag & drop a <span className="font-mono text-foreground/70">.zip</span>, or click to browse</> : <>Drag & drop a source file, or click to browse</>}</p>
                    <p className="text-xs text-muted-foreground/50">{mode === "project" ? "All supported files will be analysed — up to 50 files, 20 MB" : "Supported: .py, .js, .jsx, .ts, .tsx, .java, .go, .rs"}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {mode === "file" && (
            <>
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-foreground/[0.08] to-transparent" />
                <span className="text-xs font-medium text-muted-foreground/70">or paste code</span>
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-foreground/[0.08] to-transparent" />
              </div>
              <div>
                <label htmlFor="source-code" className="mb-2 block text-sm font-medium text-foreground/80">Source Code</label>
                <textarea id="source-code" rows={10} value={sourceCode}
                  onChange={(e) => { setSourceCode(e.target.value); if (e.target.value.trim()) setFile(null); }}
                  disabled={hasFile} placeholder="# Paste your source code here…"
                  className={cn(
                    "w-full rounded-2xl px-4 py-3 font-mono text-sm text-foreground input",
                    "disabled:cursor-not-allowed disabled:opacity-40 resize-y min-h-[140px]",
                  )} />
              </div>
            </>
          )}

          <div>
            <label className="mb-2 block text-sm font-medium text-foreground/80">LLM Provider</label>
            <div className="grid grid-cols-2 gap-2.5">
              {LLM_OPTIONS.map((opt) => {
                const isSelected = opt.value === llmProvider;
                return (
                  <button key={opt.value} type="button" onClick={() => setLlmProvider(opt.value)}
                    className={cn(
                      "relative flex items-center gap-3 rounded-2xl px-4 py-3.5 text-left text-sm transition-all duration-200",
                      isSelected
                        ? "glass-strong border-indigo-300/50 text-foreground shadow-[0_0_24px_rgba(99,102,241,0.10),0_8px_32px_rgba(0,0,0,0.06)]"
                        : "glass text-muted-foreground hover:text-foreground",
                    )}>
                    <div className={cn("h-2.5 w-2.5 rounded-full shrink-0 transition-all duration-200",
                      isSelected ? "bg-indigo-500 shadow-[0_0_10px_rgba(99,102,241,0.5),0_0_20px_rgba(99,102,241,0.2)]" : "bg-muted-foreground/20")} />
                    <span className="font-medium">{opt.label}</span>
                    {opt.badge && <span className="ml-auto text-[10px] font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-200">{opt.badge}</span>}
                  </button>
                );
              })}
            </div>
          </div>

          {errorMessage && <div className="rounded-2xl glass px-5 py-4 text-sm text-red-600 border-red-200">{errorMessage}</div>}

          <ShimmerButton disabled={!canSubmit} onClick={handleSubmit} className="w-full py-4 text-base">
            {isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> {pendingLabel}</> : <><Layers className="h-4 w-4" /> {submitLabel}</>}
          </ShimmerButton>
        </motion.div>
      </main>
    </div>
  );
}
