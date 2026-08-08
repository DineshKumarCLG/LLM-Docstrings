"""CLI entry point for VeriDoc RAG pipeline.

Run from the backend directory:
    python -m app.cli.rag_eval                          # index examples/ + run default query
    python -m app.cli.rag_eval --file path/to/code.py   # index a specific file
    python -m app.cli.rag_eval --query "Does X mutate Y?"
    python -m app.cli.rag_eval --file code.py --query "side effects?" --top-k 5 --dense-weight 0.7
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from app.rag.indexer import ASTChunker, RAGIndexer
from app.rag.reranker import Reranker
from app.rag.citation import CitationEnforcer
from app.rag.evaluator import RAGEvaluator


# ── ANSI helpers ──────────────────────────────────────────────────────────────

def _color() -> bool:
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

BOLD  = "\033[1m"  if _color() else ""
DIM   = "\033[2m"  if _color() else ""
GREEN = "\033[32m" if _color() else ""
CYAN  = "\033[36m" if _color() else ""
YELLOW= "\033[33m" if _color() else ""
RED   = "\033[31m" if _color() else ""
RESET = "\033[0m"  if _color() else ""
SEP   = "─" * 78


def heading(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{text}{RESET}")
    print(f"{DIM}{SEP}{RESET}")


def metric_line(label: str, value: float, fmt: str = ".4f", color: str = GREEN) -> None:
    bar_len = int(value * 30)
    bar = "█" * bar_len + "░" * (30 - bar_len)
    print(f"  {label:28s} {color}{value:{fmt}}{RESET}  {DIM}{bar}{RESET}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="veridoc-rag",
        description="VeriDoc RAG Pipeline — index code, retrieve, rerank, evaluate with full number breakdown.",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        nargs="+",
        help="Python source file(s) to index. Defaults to examples/ directory.",
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default="Does merge_dicts mutate its input dictionaries or return a new dict?",
        help="RAG query to execute against the indexed code.",
    )
    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=5,
        help="Number of initial retrieval candidates (default: 5).",
    )
    parser.add_argument(
        "--rerank-k",
        type=int,
        default=3,
        help="Number of chunks after re-ranking (default: 3).",
    )
    parser.add_argument(
        "--dense-weight", "-w",
        type=float,
        default=0.6,
        help="Dense vs sparse weight, 0.0=pure BM25, 1.0=pure TF-IDF (default: 0.6).",
    )
    parser.add_argument(
        "--ground-truth", "-g",
        type=str,
        default=None,
        help="Optional ground truth string for coverage metric.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full reranker score breakdown per chunk.",
    )
    args = parser.parse_args()

    # ── Resolve files ─────────────────────────────────────────────────────────
    files_map: dict[str, str] = {}

    if args.file:
        for fpath in args.file:
            p = Path(fpath)
            if not p.exists():
                print(f"{RED}Error: file not found: {fpath}{RESET}", file=sys.stderr)
                return 1
            files_map[str(p)] = p.read_text(encoding="utf-8")
    else:
        # Auto-discover examples/ or use built-in BCV sample
        examples_dir = Path(__file__).resolve().parent.parent.parent / "examples"
        if examples_dir.is_dir():
            for py_file in examples_dir.rglob("*.py"):
                rel = py_file.relative_to(examples_dir)
                files_map[f"examples/{rel}"] = py_file.read_text(encoding="utf-8")

        if not files_map:
            # Built-in BCV sample
            files_map["bcv_samples.py"] = '''
def merge_dicts(base: dict, override: dict) -> dict:
    """Return a new dictionary containing keys from both inputs.
    Neither input dictionary is modified."""
    base.update(override)
    return base

def safe_divide(a: float, b: float) -> float:
    """Divides a by b. Raises ZeroDivisionError if b is zero."""
    return a / b

def flatten_nested(data: list) -> list:
    """Flattens a nested list into a single-level list.
    Runs in O(n) time where n is total elements."""
    result = []
    for item in data:
        if isinstance(item, list):
            result.extend(flatten_nested(item))
        else:
            result.append(item)
    return result

def normalize_list(data: list[float]) -> list[float]:
    """Returns a new list with values scaled to [0, 1].
    Does not modify the input list."""
    min_val, max_val = min(data), max(data)
    for i in range(len(data)):
        data[i] = (data[i] - min_val) / (max_val - min_val)
    return data
'''

    # ── Step 1: Index ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═' * 78}{RESET}")
    print(f"{BOLD}  VeriDoc RAG Pipeline — Concrete Numbers{RESET}")
    print(f"{BOLD}{'═' * 78}{RESET}")

    heading("STEP 1 · AST Chunking & Indexing")
    indexer = RAGIndexer()
    total = indexer.index_codebase(files_map)
    for i, c in enumerate(indexer.chunks, 1):
        fn = c.function_name or "(block)"
        print(f"  {DIM}#{i}{RESET} {BOLD}{fn:24s}{RESET} {c.file_path}:{c.start_line}-{c.end_line}  {DIM}ID:{c.chunk_id}{RESET}")
    print(f"\n  {GREEN}Indexed {total} chunks{RESET} from {len(files_map)} file(s)")

    # ── Step 2: Retrieval ─────────────────────────────────────────────────────
    heading(f"STEP 2 · Hybrid Search (dense={args.dense_weight:.1f}, sparse={1-args.dense_weight:.1f})")
    print(f"  Query: {YELLOW}\"{args.query}\"{RESET}\n")

    dense_results = indexer.search_dense(args.query, top_k=args.top_k)
    sparse_results = indexer.search_sparse(args.query, top_k=args.top_k)
    hybrid_results = indexer.hybrid_search(args.query, top_k=args.top_k, dense_weight=args.dense_weight)

    print(f"  {'Function':<24s} {'Dense':>8s} {'Sparse':>8s} {'Hybrid':>8s}")
    print(f"  {'─'*24} {'─'*8} {'─'*8} {'─'*8}")
    for c, h_score in hybrid_results:
        d = next((s for ch, s in dense_results if ch.chunk_id == c.chunk_id), 0.0)
        s = next((s for ch, s in sparse_results if ch.chunk_id == c.chunk_id), 0.0)
        fn = c.function_name or "(block)"
        print(f"  {fn:<24s} {d:>8.4f} {s:>8.4f} {GREEN}{h_score:>8.4f}{RESET}")

    # ── Step 3: Re-ranking ────────────────────────────────────────────────────
    heading(f"STEP 3 · Re-ranker (top {args.rerank_k}, scores ∈ [0, 1])")
    reranker = Reranker()
    reranked = reranker.rerank(args.query, hybrid_results, top_k=args.rerank_k)

    query_terms = set(re.findall(r"\w+", args.query.lower()))
    contract_kw = {"return", "returns", "raises", "raise", "param", "params", "mutates", "contract", "bcv"}

    for c, score in reranked:
        fn = c.function_name or "(block)"
        print(f"\n  {BOLD}{fn}{RESET}  →  {GREEN}{score:.6f}{RESET}")

        if args.verbose:
            initial = next((s for ch, s in hybrid_results if ch.chunk_id == c.chunk_id), 0.0)
            clamped = max(0.0, min(1.0, initial))
            content_terms = set(re.findall(r"\w+", c.content.lower()))
            overlap = len(query_terms.intersection(content_terms)) / (len(query_terms) or 1)
            sig = 1.0 if (c.function_name and c.function_name.lower() in args.query.lower()) else 0.0
            doc = 1.0 if (c.docstring and any(t in c.docstring.lower() for t in query_terms)) else 0.0
            sig_score = sig * 0.6 + doc * 0.4
            con = 1.0 if any(k in c.content.lower() for k in contract_kw) else 0.0

            print(f"    {DIM}0.30 × initial({clamped:.4f}) = {0.30*clamped:.4f}{RESET}")
            print(f"    {DIM}0.30 × overlap({overlap:.4f}) = {0.30*overlap:.4f}{RESET}")
            print(f"    {DIM}0.25 × sig/doc({sig_score:.4f}) = {0.25*sig_score:.4f}{RESET}")
            print(f"    {DIM}0.15 × contract({con:.4f}) = {0.15*con:.4f}{RESET}")

        assert 0.0 <= score <= 1.0, f"Score {score} out of bounds!"

    # ── Step 4: Citation ──────────────────────────────────────────────────────
    heading("STEP 4 · Citation Enforcement")
    reranked_chunks = [c for c, _ in reranked]
    primary = reranked_chunks[0]
    cite = f"[Source: {primary.file_path}:{primary.start_line}-{primary.end_line} | ID: {primary.chunk_id}]"

    # Generate grounded response
    findings = []
    for c in reranked_chunks:
        tag = f"[Source: {c.file_path}:{c.start_line}-{c.end_line} | ID: {c.chunk_id}]"
        fn = f"function `{c.function_name}`" if c.function_name else f"code in `{c.file_path}`"
        doc = f" — docstring: '{c.docstring[:60]}'" if c.docstring else ""
        findings.append(f"Analyzed {fn}{doc}. {tag}")

    response_text = " ".join(findings)

    _, is_compliant, stats = CitationEnforcer.verify_citations(response_text, reranked_chunks)
    print(f"  Citations found  : {stats['total_citations']}")
    print(f"  Valid citations  : {stats['valid_citations']}")
    print(f"  Compliance rate  : {GREEN}{stats['compliance_rate']:.4f}{RESET}")
    print(f"  Compliant (≥75%) : {'✓ Yes' if stats['is_compliant'] else '✗ No'}")

    # ── Step 5: Evaluation Metrics ────────────────────────────────────────────
    heading("STEP 5 · Heuristic Quality Metrics (term-overlap, NOT RAGAS)")
    eval_res = RAGEvaluator.evaluate(
        query=args.query,
        response=response_text,
        retrieved_chunks=reranked_chunks,
        ground_truth=args.ground_truth,
    )

    metric_line("Grounding Ratio",      eval_res.grounding_ratio)
    metric_line("Retrieval Hit Rate",   eval_res.retrieval_hit_rate)
    metric_line("Ground Truth Coverage", eval_res.ground_truth_coverage)
    metric_line("Query Term Echo",      eval_res.query_term_echo)
    metric_line("Citation Compliance",  eval_res.citation_compliance)

    print()
    print(f"  {DIM}Composite = (0.30×grounding) + (0.25×citation) + (0.20×hit_rate) + (0.15×echo) + (0.10×gt_coverage){RESET}")
    manual = (
        0.30 * eval_res.grounding_ratio
        + 0.25 * eval_res.citation_compliance
        + 0.20 * eval_res.retrieval_hit_rate
        + 0.15 * eval_res.query_term_echo
        + 0.10 * eval_res.ground_truth_coverage
    )
    print(f"  {DIM}= (0.30×{eval_res.grounding_ratio:.4f}) + (0.25×{eval_res.citation_compliance:.4f}) + (0.20×{eval_res.retrieval_hit_rate:.4f}) + (0.15×{eval_res.query_term_echo:.4f}) + (0.10×{eval_res.ground_truth_coverage:.4f}){RESET}")

    metric_line("COMPOSITE SCORE",      eval_res.composite_heuristic_score, color=YELLOW)

    # ── Verification ──────────────────────────────────────────────────────────
    heading("VERIFICATION")
    all_ok = True
    for name, val in [
        ("grounding_ratio", eval_res.grounding_ratio),
        ("retrieval_hit_rate", eval_res.retrieval_hit_rate),
        ("ground_truth_coverage", eval_res.ground_truth_coverage),
        ("query_term_echo", eval_res.query_term_echo),
        ("citation_compliance", eval_res.citation_compliance),
        ("composite_heuristic_score", eval_res.composite_heuristic_score),
    ]:
        ok = 0.0 <= val <= 1.0
        mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {mark} {name:30s} = {val:.4f}  ∈ [0, 1]")
        if not ok:
            all_ok = False

    for c, s in reranked:
        ok = 0.0 <= s <= 1.0
        mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        fn = c.function_name or "(block)"
        print(f"  {mark} rerank({fn:20s}) = {s:.4f}  ∈ [0, 1]")
        if not ok:
            all_ok = False

    print(f"\n{'═' * 78}")
    if all_ok:
        print(f"  {GREEN}{BOLD}ALL SCORES VALID — EVERY NUMBER ∈ [0, 1]{RESET}")
    else:
        print(f"  {RED}{BOLD}SOME SCORES OUT OF BOUNDS{RESET}")
    print(f"{'═' * 78}\n")

    return 0 if all_ok else 1



if __name__ == "__main__":
    sys.exit(main())
