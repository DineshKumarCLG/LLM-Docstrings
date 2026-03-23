import { useState, useCallback, useRef } from "react";
import { FolderOpen, FileCode, AlertTriangle, X, ChevronRight, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileWithPath, SupportedLanguage } from "@/types";

const SUPPORTED_EXTENSIONS: Record<string, SupportedLanguage> = {
  ".py": "python", ".js": "javascript", ".jsx": "javascript",
  ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".go": "go", ".rs": "rust",
};
const LANGUAGE_LABELS: Record<SupportedLanguage, { label: string; color: string }> = {
  python: { label: "PY", color: "text-blue-600" }, javascript: { label: "JS", color: "text-yellow-600" },
  typescript: { label: "TS", color: "text-blue-500" }, java: { label: "JV", color: "text-orange-600" },
  go: { label: "GO", color: "text-cyan-600" }, rust: { label: "RS", color: "text-red-600" },
};
const DEFAULT_MAX_FILES = 50;
const DEFAULT_MAX_TOTAL_SIZE = 20 * 1024 * 1024;

interface FolderPickerProps { onFilesSelected: (files: FileWithPath[]) => void; maxFiles?: number; maxTotalSize?: number; }
interface TreeNode { name: string; fileWithPath?: FileWithPath; children: Map<string, TreeNode>; }

function detectLanguage(filename: string): SupportedLanguage | null {
  const idx = filename.lastIndexOf(".");
  return idx === -1 ? null : (SUPPORTED_EXTENSIONS[filename.slice(idx).toLowerCase()] ?? null);
}
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function buildTree(files: FileWithPath[]): TreeNode {
  const root: TreeNode = { name: "", children: new Map() };
  for (const f of files) {
    const parts = f.relativePath.split("/");
    let node = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]!;
      if (!node.children.has(part)) node.children.set(part, { name: part, children: new Map(), fileWithPath: i === parts.length - 1 ? f : undefined });
      node = node.children.get(part)!;
    }
  }
  return root;
}

function TreeNodeView({ node, depth = 0 }: { node: TreeNode; depth?: number }) {
  const [expanded, setExpanded] = useState(true);
  const isDir = !node.fileWithPath && node.children.size > 0;
  const children = Array.from(node.children.values()).sort((a, b) => {
    const aDir = !a.fileWithPath ? 0 : 1;
    const bDir = !b.fileWithPath ? 0 : 1;
    if (aDir !== bDir) return aDir - bDir;
    return a.name.localeCompare(b.name);
  });

  if (isDir) {
    return (
      <div>
        <button type="button" onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 w-full text-left py-0.5 hover:bg-foreground/[0.03] rounded px-1 text-sm text-muted-foreground"
          style={{ paddingLeft: `${depth * 16 + 4}px` }}>
          {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
          <FolderOpen className="h-3.5 w-3.5 shrink-0 text-indigo-500/70" />
          <span className="truncate">{node.name}</span>
        </button>
        {expanded && children.map((child) => <TreeNodeView key={child.name} node={child} depth={depth + 1} />)}
      </div>
    );
  }
  const lang = node.fileWithPath ? LANGUAGE_LABELS[node.fileWithPath.language] : null;
  return (
    <div className="flex items-center gap-1.5 py-0.5 px-1 text-sm" style={{ paddingLeft: `${depth * 16 + 24}px` }}>
      <FileCode className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
      <span className="truncate text-foreground/80">{node.name}</span>
      {lang && <span className={cn("ml-auto text-[10px] font-semibold shrink-0", lang.color)}>{lang.label}</span>}
    </div>
  );
}

export default function FolderPicker({ onFilesSelected, maxFiles = DEFAULT_MAX_FILES, maxTotalSize = DEFAULT_MAX_TOTAL_SIZE }: FolderPickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<FileWithPath[]>([]);
  const [skippedCount, setSkippedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const totalSize = selectedFiles.reduce((sum, f) => sum + f.file.size, 0);

  const processFiles = useCallback((fileList: FileList) => {
    const supported: FileWithPath[] = [];
    let skipped = 0;
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList.item(i);
      if (!file) continue;
      const relativePath = file.webkitRelativePath || file.name;
      const lang = detectLanguage(file.name);
      if (lang) supported.push({ file, relativePath, language: lang });
      else skipped++;
    }
    const total = supported.reduce((s, f) => s + f.file.size, 0);
    if (supported.length > maxFiles) { setError(`Too many files (${supported.length}). Max is ${maxFiles}.`); setSelectedFiles([]); setSkippedCount(skipped); onFilesSelected([]); return; }
    if (total > maxTotalSize) { setError(`Total size ${formatSize(total)} exceeds ${formatSize(maxTotalSize)} limit.`); setSelectedFiles([]); setSkippedCount(skipped); onFilesSelected([]); return; }
    setError(null); setSkippedCount(skipped); setSelectedFiles(supported); onFilesSelected(supported);
  }, [maxFiles, maxTotalSize, onFilesSelected]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => { const files = e.target.files; if (files && files.length > 0) processFiles(files); }, [processFiles]);
  const clearSelection = useCallback(() => { setSelectedFiles([]); setSkippedCount(0); setError(null); onFilesSelected([]); if (inputRef.current) inputRef.current.value = ""; }, [onFilesSelected]);
  const tree = selectedFiles.length > 0 ? buildTree(selectedFiles) : null;

  return (
    <div className="space-y-3">
      <input ref={inputRef} type="file" className="hidden" onChange={handleInputChange}
        /* @ts-expect-error webkitdirectory is non-standard but widely supported */
        webkitdirectory="" aria-label="Select folder" />

      {selectedFiles.length === 0 && !error ? (
        <button type="button" onClick={() => inputRef.current?.click()}
          className={cn("flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-10",
            "border-foreground/[0.08] hover:border-indigo-400/30 hover:bg-foreground/[0.02] transition-all duration-200")}>
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl skeu-raised"><FolderOpen className="h-5 w-5 text-muted-foreground" /></div>
          <p className="text-sm text-muted-foreground">Click to select a folder</p>
          <p className="text-xs text-muted-foreground/50">Supported: .py, .js, .ts, .tsx, .jsx, .java, .go, .rs — up to {maxFiles} files, {formatSize(maxTotalSize)}</p>
        </button>
      ) : (
        <div className="rounded-2xl glass">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-foreground/[0.06]">
            <div className="flex items-center gap-2 text-sm">
              <FolderOpen className="h-4 w-4 text-indigo-500" />
              <span className="font-medium">{selectedFiles.length} file{selectedFiles.length !== 1 ? "s" : ""}</span>
              <span className="text-muted-foreground">({formatSize(totalSize)})</span>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => inputRef.current?.click()} className="text-xs text-indigo-500 hover:text-indigo-600 transition-colors">Change</button>
              <button type="button" onClick={clearSelection} className="rounded-lg p-1 text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground transition-colors" aria-label="Clear selection"><X className="h-3.5 w-3.5" /></button>
            </div>
          </div>
          {tree && <div className="max-h-64 overflow-y-auto px-2 py-2">{Array.from(tree.children.values()).map((child) => <TreeNodeView key={child.name} node={child} />)}</div>}
          {skippedCount > 0 && (
            <div className="flex items-center gap-2 px-4 py-2 border-t border-foreground/[0.06] text-xs text-muted-foreground">
              <AlertTriangle className="h-3.5 w-3.5 text-yellow-500/70" />
              {skippedCount} file{skippedCount !== 1 ? "s" : ""} skipped (unsupported)
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-2xl glass px-4 py-3 text-sm text-red-600 border-red-500/20">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <p>{error}</p>
            <button type="button" onClick={() => inputRef.current?.click()} className="mt-1 text-xs underline hover:text-red-500 transition-colors">Try a different folder</button>
          </div>
        </div>
      )}
    </div>
  );
}
