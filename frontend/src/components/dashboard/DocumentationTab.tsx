import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, FileText, Code2, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDocumentation } from "@/hooks/useAnalysis";
import type { AnalysisStatus, DocumentationNode } from "@/types";

export interface DocumentationTabProps {
  analysisId: string;
  analysisStatus: AnalysisStatus;
}

function SignatureHighlight({ signature }: { signature: string }) {
  const match = signature.match(/^([^(]+)(\([^)]*\))(.*)$/);
  if (!match) return <code className="text-xs font-mono text-muted-foreground">{signature}</code>;
  const [, name, params, rest] = match;
  const arrowMatch = rest?.match(/^(\s*->\s*)(.+)$/);
  return (
    <code className="text-xs font-mono">
      <span className="text-blue-600">{name}</span>
      <span className="text-amber-600">{params}</span>
      {arrowMatch ? (
        <><span className="text-muted-foreground">{arrowMatch[1]}</span><span className="text-emerald-600">{arrowMatch[2]}</span></>
      ) : (
        <span className="text-muted-foreground">{rest}</span>
      )}
    </code>
  );
}

function NodeIcon({ type }: { type: DocumentationNode["type"] }) {
  if (type === "class") return <Code2 className="h-4 w-4 shrink-0 text-purple-600" aria-hidden="true" />;
  return <FileText className="h-4 w-4 shrink-0 text-blue-600" aria-hidden="true" />;
}

function DocNode({ node, depth = 0 }: { node: DocumentationNode; depth?: number }) {
  const hasChildren = node.children.length > 0;
  const [expanded, setExpanded] = useState(node.type === "class");

  return (
    <div className={cn("border-l border-foreground/[0.06]", depth > 0 && "ml-4")}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          "flex w-full items-start gap-2 px-3 py-2 text-left",
          "hover:bg-foreground/[0.03] transition-colors duration-100 rounded-r-lg",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
        aria-expanded={expanded}
      >
        <motion.span
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 25 }}
          className="mt-0.5 shrink-0 text-muted-foreground"
        >
          {hasChildren ? <ChevronRight className="h-3.5 w-3.5" /> : <span className="inline-block h-3.5 w-3.5" />}
        </motion.span>
        <NodeIcon type={node.type} />
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-foreground">{node.name}</span>
            <span className={cn(
              "rounded-lg px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
              node.type === "class" && "bg-purple-500/15 text-purple-600",
              node.type === "function" && "bg-blue-500/15 text-blue-600",
              node.type === "method" && "bg-emerald-500/15 text-emerald-600",
              node.type === "module" && "bg-amber-500/15 text-amber-600",
            )}>{node.type}</span>
            {node.lineno > 0 && <span className="text-[10px] text-muted-foreground">L{node.lineno}{node.endLineno ? `–${node.endLineno}` : ""}</span>}
          </div>
          {node.signature && <div className="mt-0.5"><SignatureHighlight signature={node.signature} /></div>}
        </div>
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="overflow-hidden pl-3"
          >
            {node.docstring && (
              <pre className={cn("mx-3 mb-2 mt-1 overflow-x-auto rounded-xl skeu-inset px-4 py-3 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap font-mono")}>{node.docstring}</pre>
            )}
            {hasChildren && node.children.map((child) => <DocNode key={child.id} node={child} depth={depth + 1} />)}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function DocumentationTab({ analysisId, analysisStatus }: DocumentationTabProps) {
  const isComplete = analysisStatus === "complete";
  const { data: tree, isLoading, isError } = useDocumentation(analysisId, analysisStatus);

  if (!isComplete) {
    return (
      <div className="rounded-2xl glass px-6 py-12 text-center">
        <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium text-foreground">Analysis in progress</p>
        <p className="mt-1 text-xs text-muted-foreground">Documentation will be available once the pipeline completes.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="rounded-2xl glass px-6 py-12 text-center">
        <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">Loading documentation…</p>
      </div>
    );
  }

  if (isError || !tree) {
    return (
      <div className="rounded-2xl glass px-6 py-12 text-center">
        <AlertCircle className="mx-auto mb-3 h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium text-foreground">Documentation unavailable</p>
        <p className="mt-1 text-xs text-muted-foreground">Unable to load the documentation tree.</p>
      </div>
    );
  }

  if (tree.rootNodes.length === 0) {
    return (
      <div className="rounded-2xl glass px-6 py-12 text-center">
        <FileText className="mx-auto mb-3 h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium text-foreground">No documented entities found</p>
        <p className="mt-1 text-xs text-muted-foreground">The source file does not contain any documented functions or classes.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {tree.rootNodes.length} top-level {tree.rootNodes.length === 1 ? "entity" : "entities"} · generated {new Date(tree.generatedAt).toLocaleString()}
        </p>
      </div>
      <div className="rounded-2xl glass overflow-hidden">
        {tree.rootNodes.map((node) => <DocNode key={node.id} node={node} depth={0} />)}
      </div>
    </div>
  );
}
