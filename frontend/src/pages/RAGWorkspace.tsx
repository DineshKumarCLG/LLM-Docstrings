import React, { useState, useEffect } from "react";
import { ragApi } from "@/api/client";
import type { RAGQueryResult, RAGStats, RAGChunk } from "@/types";
import {
  Database,
  Search,
  FileCode,
  Sparkles,
  Sliders,
  BarChart3,
  RefreshCw,
  Quote,
  ShieldCheck,
  Layers,
  BookOpen,
} from "lucide-react";

export const RAGWorkspace: React.FC = () => {
  const [stats, setStats] = useState<RAGStats | null>(null);
  const [indexing, setIndexing] = useState<boolean>(false);

  // Search state
  const [query, setQuery] = useState<string>("Does normalize_list mutate arguments or return a new list?");
  const [denseWeight, setDenseWeight] = useState<number>(0.6);
  const [topKRetrieval, setTopKRetrieval] = useState<number>(5);
  const [topKRerank, setTopKRerank] = useState<number>(3);
  const [llmProvider, setLlmProvider] = useState<string>("auto");
  const [groundTruth] = useState<string>("");
  const [searching, setSearching] = useState<boolean>(false);
  const [queryResult, setQueryResult] = useState<RAGQueryResult | null>(null);

  // Active tab
  const [activeTab, setActiveTab] = useState<"query" | "eval" | "index">("query");
  const [, setSelectedChunk] = useState<RAGChunk | null>(null);

  const fetchStats = async () => {
    try {
      const res = await ragApi.getStats();
      setStats(res.data);
    } catch (err) {
      console.error("Failed to load RAG stats:", err);
    }
  };

  const handleIndexCodebase = async () => {
    setIndexing(true);
    try {
      await ragApi.index();
      await fetchStats();
    } catch (err) {
      console.error("Failed to index codebase:", err);
    } finally {
      setIndexing(false);
    }
  };

  const handleExecuteQuery = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setSearching(true);
    try {
      const res = await ragApi.query({
        query,
        dense_weight: denseWeight,
        top_k_retrieval: topKRetrieval,
        top_k_rerank: topKRerank,
        llm_provider: llmProvider,
        ground_truth: groundTruth.trim() ? groundTruth : undefined,
      });
      setQueryResult(res.data);
      if (res.data.reranked_chunks.length > 0) {
        setSelectedChunk(res.data.reranked_chunks[0] || null);
      }
      fetchStats();
    } catch (err) {
      console.error("RAG Query failed:", err);
    } finally {
      setSearching(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  // Helper to render citation badges in text
  const renderGroundedAnswer = (answerText: string) => {
    const parts = answerText.split(/(\[Source:\s*[^\]]+\])/g);
    return parts.map((part, i) => {
      if (part.startsWith("[Source:")) {
        return (
          <span
            key={i}
            className="inline-flex items-center gap-1 mx-1 px-2 py-0.5 text-xs font-mono rounded bg-blue-500/10 text-blue-400 border border-blue-500/30 cursor-pointer hover:bg-blue-500/20 transition-colors"
            title="Click to view citation chunk source"
          >
            <Quote className="w-3 h-3 text-blue-400" />
            {part.replace(/\[Source:\s*|\s*\]/g, "")}
          </span>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto p-6 text-slate-100">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/80 p-6 rounded-2xl border border-slate-800 backdrop-blur">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-600/20 rounded-xl border border-blue-500/30 text-blue-400">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">
                VeriDoc RAG & Evaluation Engine
              </h1>
              <p className="text-sm text-slate-400">
                Hybrid Vector Retrieval, Cross-Encoder Re-ranking, Citation Enforcement & RAG Quality Metrics
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleIndexCodebase}
            disabled={indexing}
            className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 font-medium text-white text-sm rounded-xl transition-all shadow-lg shadow-blue-600/20"
          >
            <RefreshCw className={`w-4 h-4 ${indexing ? "animate-spin" : ""}`} />
            {indexing ? "Indexing Codebase..." : "Re-Index Codebase"}
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/60 p-5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Indexed Chunks</span>
            <Layers className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-2">
            {stats ? stats.total_chunks : 0}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            Across {stats ? stats.files_indexed : 0} files
          </div>
        </div>

        <div className="bg-slate-900/60 p-5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Avg Faithfulness</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 mt-2">
            {stats ? `${(stats.metrics_summary.average_faithfulness * 100).toFixed(1)}%` : "N/A"}
          </div>
          <div className="text-xs text-slate-500 mt-1">Grounding consistency</div>
        </div>

        <div className="bg-slate-900/60 p-5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Citation Compliance</span>
            <Quote className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-purple-400 mt-2">
            {stats ? `${(stats.metrics_summary.average_citation_compliance * 100).toFixed(1)}%` : "N/A"}
          </div>
          <div className="text-xs text-slate-500 mt-1">Enforced source references</div>
        </div>

        <div className="bg-slate-900/60 p-5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Overall RAG Score</span>
            <Sparkles className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400 mt-2">
            {stats ? stats.metrics_summary.average_overall_rag_score.toFixed(3) : "N/A"}
          </div>
          <div className="text-xs text-slate-500 mt-1">Composite benchmark rating</div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800">
        <button
          onClick={() => setActiveTab("query")}
          className={`flex items-center gap-2 px-6 py-3 border-b-2 font-medium text-sm transition-colors ${
            activeTab === "query"
              ? "border-blue-500 text-blue-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <Search className="w-4 h-4" />
          RAG Query & Citation Search
        </button>
        <button
          onClick={() => setActiveTab("eval")}
          className={`flex items-center gap-2 px-6 py-3 border-b-2 font-medium text-sm transition-colors ${
            activeTab === "eval"
              ? "border-blue-500 text-blue-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          RAG Evaluation Suite
        </button>
        <button
          onClick={() => setActiveTab("index")}
          className={`flex items-center gap-2 px-6 py-3 border-b-2 font-medium text-sm transition-colors ${
            activeTab === "index"
              ? "border-blue-500 text-blue-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <BookOpen className="w-4 h-4" />
          Vector Store Index ({stats ? stats.files_indexed : 0} Files)
        </button>
      </div>

      {/* TAB 1: RAG QUERY & CITATION SEARCH */}
      {activeTab === "query" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Query Form & Controls */}
          <div className="lg:col-span-5 space-y-5 bg-slate-900/70 p-6 rounded-2xl border border-slate-800">
            <form onSubmit={handleExecuteQuery} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                  Codebase Query / Contract Assertion
                </label>
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  rows={3}
                  placeholder="e.g. Does normalize_list mutate arguments in place or raise exceptions?"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors resize-none"
                />
              </div>

              {/* Retrieval & Re-ranking Controls */}
              <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800/80 space-y-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-blue-400 uppercase tracking-wider">
                  <Sliders className="w-4 h-4" />
                  <span>Retrieval & Re-ranking Settings</span>
                </div>

                {/* Dense vs Sparse Slider */}
                <div>
                  <div className="flex justify-between text-xs text-slate-300 mb-1">
                    <span>Dense Vector vs BM25 Keyword</span>
                    <span className="font-mono text-blue-400">
                      Dense: {(denseWeight * 100).toFixed(0)}% / BM25: {((1 - denseWeight) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={denseWeight}
                    onChange={(e) => setDenseWeight(parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                  />
                </div>

                {/* Top-K Retrieval & Rerank */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Top-K Retrieval</label>
                    <select
                      value={topKRetrieval}
                      onChange={(e) => setTopKRetrieval(parseInt(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                    >
                      <option value={3}>3 Chunks</option>
                      <option value={5}>5 Chunks</option>
                      <option value={10}>10 Chunks</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Top-K Re-ranked</label>
                    <select
                      value={topKRerank}
                      onChange={(e) => setTopKRerank(parseInt(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                    >
                      <option value={1}>1 Top Chunk</option>
                      <option value={2}>2 Top Chunks</option>
                      <option value={3}>3 Top Chunks</option>
                    </select>
                  </div>
                </div>

                {/* LLM Provider */}
                <div>
                  <label className="block text-xs text-slate-400 mb-1">LLM Provider</label>
                  <select
                    value={llmProvider}
                    onChange={(e) => setLlmProvider(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                  >
                    <option value="auto">Auto (Configured API / Grounded Engine)</option>
                    <option value="openai">OpenAI (GPT-4o Mini)</option>
                    <option value="google">Google Gemini (2.5 Flash)</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                disabled={searching}
                className="w-full flex items-center justify-center gap-2 py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium text-sm rounded-xl transition-all shadow-lg shadow-blue-600/20"
              >
                <Search className={`w-4 h-4 ${searching ? "animate-spin" : ""}`} />
                {searching ? "Retrieving, Reranking & Verifying..." : "Execute Grounded RAG Query"}
              </button>
            </form>
          </div>

          {/* RAG Output & Grounded Answer */}
          <div className="lg:col-span-7 space-y-6">
            {queryResult ? (
              <>
                {/* Answer Card */}
                <div className="bg-slate-900/70 p-6 rounded-2xl border border-slate-800 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div className="flex items-center gap-2 text-emerald-400 font-semibold text-sm">
                      <ShieldCheck className="w-5 h-5" />
                      <span>Grounded Response with Enforced Citations</span>
                    </div>
                    {queryResult.citations && (
                      <span
                        className={`text-xs px-2.5 py-1 rounded-full font-mono font-medium border ${
                          queryResult.citations.is_compliant
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        }`}
                      >
                        Citation Compliance: {(queryResult.citations.compliance_rate * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>

                  <div className="prose prose-invert max-w-none text-sm leading-relaxed text-slate-200 whitespace-pre-wrap font-sans">
                    {renderGroundedAnswer(queryResult.answer)}
                  </div>
                </div>

                {/* Evaluation Scorecard */}
                {queryResult.evaluation && (
                  <div className="bg-slate-900/70 p-5 rounded-2xl border border-slate-800 space-y-3">
                    <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-amber-400" />
                      <span>Real-time RAG Evaluation Metrics</span>
                    </div>
                    <div className="grid grid-cols-5 gap-2 text-center">
                      <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-xs text-slate-400">Faithfulness</div>
                        <div className="text-sm font-bold text-emerald-400 mt-1">
                          {(queryResult.evaluation.faithfulness * 100).toFixed(0)}%
                        </div>
                      </div>
                      <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-xs text-slate-400">Precision</div>
                        <div className="text-sm font-bold text-blue-400 mt-1">
                          {(queryResult.evaluation.context_precision * 100).toFixed(0)}%
                        </div>
                      </div>
                      <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-xs text-slate-400">Recall</div>
                        <div className="text-sm font-bold text-purple-400 mt-1">
                          {(queryResult.evaluation.context_recall * 100).toFixed(0)}%
                        </div>
                      </div>
                      <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-xs text-slate-400">Relevance</div>
                        <div className="text-sm font-bold text-indigo-400 mt-1">
                          {(queryResult.evaluation.answer_relevance * 100).toFixed(0)}%
                        </div>
                      </div>
                      <div className="bg-slate-950 p-2.5 rounded-lg border border-amber-500/30">
                        <div className="text-xs text-amber-400">Overall</div>
                        <div className="text-sm font-bold text-amber-400 mt-1">
                          {queryResult.evaluation.overall_rag_score.toFixed(3)}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Re-ranked Context Chunks */}
                <div className="bg-slate-900/70 p-5 rounded-2xl border border-slate-800 space-y-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                    <FileCode className="w-4 h-4 text-blue-400" />
                    <span>Top Re-ranked Chunks ({queryResult.reranked_chunks.length})</span>
                  </h3>
                  <div className="space-y-3">
                    {queryResult.reranked_chunks.map((chunk: RAGChunk, idx: number) => (
                      <div
                        key={idx}
                        className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono text-blue-400 font-semibold">
                            {chunk.file_path}:{chunk.start_line}-{chunk.end_line}
                          </span>
                          <span className="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded font-mono border border-blue-500/20">
                            Re-rank Score: {chunk.rerank_score}
                          </span>
                        </div>
                        {chunk.function_name && (
                          <div className="text-xs text-slate-300">
                            Function: <code className="text-amber-300 font-mono">{chunk.function_name}</code>
                          </div>
                        )}
                        <pre className="p-3 bg-slate-900 rounded-lg text-xs font-mono text-slate-300 overflow-x-auto border border-slate-800/80">
                          {chunk.content}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="bg-slate-900/40 p-12 rounded-2xl border border-slate-800/80 text-center text-slate-500 space-y-3">
                <Search className="w-12 h-12 mx-auto text-slate-700" />
                <p className="text-sm">Submit a query to see grounded RAG search results with re-ranking and citation enforcement.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: EVALUATION SUITE */}
      {activeTab === "eval" && (
        <div className="bg-slate-900/70 p-6 rounded-2xl border border-slate-800 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">RAG Evaluation Suite & Benchmark History</h2>
              <p className="text-xs text-slate-400">Automated evaluation tracking Faithfulness, Context Precision/Recall, and Citation Compliance across query runs.</p>
            </div>
          </div>

          {stats && stats.recent_evaluations.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 uppercase font-semibold border-b border-slate-800">
                  <tr>
                    <th className="p-3">Query</th>
                    <th className="p-3 text-center">Faithfulness</th>
                    <th className="p-3 text-center">Context Precision</th>
                    <th className="p-3 text-center">Citation Compliance</th>
                    <th className="p-3 text-center">Relevance</th>
                    <th className="p-3 text-center">Overall Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {stats.recent_evaluations.map((item: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="p-3 font-medium text-slate-100 max-w-xs truncate">{item.query}</td>
                      <td className="p-3 text-center font-mono text-emerald-400">{(item.faithfulness * 100).toFixed(0)}%</td>
                      <td className="p-3 text-center font-mono text-blue-400">{(item.context_precision * 100).toFixed(0)}%</td>
                      <td className="p-3 text-center font-mono text-purple-400">{(item.citation_compliance * 100).toFixed(0)}%</td>
                      <td className="p-3 text-center font-mono text-indigo-400">{(item.answer_relevance * 100).toFixed(0)}%</td>
                      <td className="p-3 text-center font-mono font-bold text-amber-400">{item.overall_rag_score.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-slate-500 text-sm">
              No evaluation history recorded yet. Run a RAG query to generate real-time evaluation metrics.
            </div>
          )}
        </div>
      )}

      {/* TAB 3: INDEX EXPLORER */}
      {activeTab === "index" && (
        <div className="bg-slate-900/70 p-6 rounded-2xl border border-slate-800 space-y-4">
          <h2 className="text-lg font-bold text-white">Indexed Files ({stats ? stats.indexed_file_list.length : 0})</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {stats && stats.indexed_file_list.map((file: string, idx: number) => (
              <div key={idx} className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileCode className="w-5 h-5 text-blue-400" />
                  <span className="font-mono text-xs text-slate-200">{file}</span>
                </div>
                <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded font-mono">
                  Indexed
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
