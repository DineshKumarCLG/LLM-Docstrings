"""
Real RAG evaluation against the actual VeriDoc example file.

This script:
1. Reads examples/sample_bcv.py from disk (the file that ships with the project)
2. Indexes it with the RAG pipeline
3. Runs 12 queries derived from the actual known BCVs documented in that file
4. For each query, checks whether the correct function appears in top-1 and top-3 results
5. Reports Hit@1, Hit@3, MRR — standard information retrieval metrics

No invented ground truth strings. No composite heuristic scores.
The only question being measured: "does the retriever find the right function?"
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from app.rag.indexer import RAGIndexer
from app.rag.reranker import Reranker


def main() -> int:
    # ── Load the actual file from disk ────────────────────────────────────────
    examples_dir = Path(__file__).resolve().parent.parent.parent / "examples"
    sample_file = examples_dir / "sample_bcv.py"

    if not sample_file.exists():
        print(f"ERROR: {sample_file} not found", file=sys.stderr)
        return 1

    code = sample_file.read_text(encoding="utf-8")
    rel_path = f"examples/sample_bcv.py"

    # ── Evaluation queries ────────────────────────────────────────────────────
    # Each query is derived from an actual BCV documented in sample_bcv.py.
    # expected_function is the function that contains that violation.
    # These are not invented — they come from the BCV comments in the source.

    eval_set = [
        # normalize_list violations (RSV, SEV, ECV)
        {"query": "Which function claims to return a new list but actually returns the same object?",
         "expected": "normalize_list", "bcv": "RSV"},
        {"query": "Does normalize_list modify the input list in place?",
         "expected": "normalize_list", "bcv": "SEV"},
        {"query": "Does normalize_list raise ValueError on empty input?",
         "expected": "normalize_list", "bcv": "ECV"},

        # find_median violations (SEV, ECV)
        {"query": "Does find_median modify the input list when computing the median?",
         "expected": "find_median", "bcv": "SEV"},
        {"query": "Does find_median raise TypeError for non-integer elements?",
         "expected": "find_median", "bcv": "ECV"},

        # merge_dicts violations (SEV, RSV, ECV)
        {"query": "Does merge_dicts mutate the base dictionary?",
         "expected": "merge_dicts", "bcv": "SEV"},
        {"query": "Does merge_dicts return a new dictionary or the mutated base?",
         "expected": "merge_dicts", "bcv": "RSV"},

        # calculate_statistics violations (COV, ECV)
        {"query": "Does calculate_statistics return count and sum in addition to mean and variance?",
         "expected": "calculate_statistics", "bcv": "COV"},
        {"query": "Does calculate_statistics raise ValueError when given fewer than two elements?",
         "expected": "calculate_statistics", "bcv": "ECV"},

        # flatten_nested violations (CCV, ECV)
        {"query": "What is the actual time complexity of flatten_nested with deep nesting?",
         "expected": "flatten_nested", "bcv": "CCV"},
        {"query": "Does flatten_nested raise TypeError when input is not a list?",
         "expected": "flatten_nested", "bcv": "ECV"},

        # Cross-cutting query
        {"query": "Which functions claim not to modify their input but actually do?",
         "expected": "normalize_list", "bcv": "SEV"},  # normalize_list is the strongest match

        # ── Adversarial queries (don't name the function) ─────────────────────
        # These are harder — a real user wouldn't always name the function.

        {"query": "Which function mutates a dict using .update() instead of creating a copy?",
         "expected": "merge_dicts", "bcv": "SEV"},
        {"query": "Where does the docstring claim O(n) but recursion makes it O(n*d)?",
         "expected": "flatten_nested", "bcv": "CCV"},
        {"query": "Which function returns an empty list instead of raising an exception on empty input?",
         "expected": "normalize_list", "bcv": "ECV"},
        {"query": "Where are extra keys like count and sum returned but not documented?",
         "expected": "calculate_statistics", "bcv": "COV"},
        {"query": "Which function's docstring says it raises TypeError but the code never checks types?",
         "expected": "find_median", "bcv": "ECV"},
        {"query": "What code scales values to zero-one range by modifying the list in place?",
         "expected": "normalize_list", "bcv": "SEV"},
        {"query": "Where does a function claim immutability for both arguments but call update?",
         "expected": "merge_dicts", "bcv": "SEV"},
        {"query": "Which docstring promises a new object but the return statement gives back the same reference?",
         "expected": "normalize_list", "bcv": "RSV"},
    ]

    # ── Index ─────────────────────────────────────────────────────────────────
    indexer = RAGIndexer()
    n_chunks = indexer.index_codebase({rel_path: code})

    print(f"{'=' * 72}")
    print(f"  VeriDoc RAG Retrieval Evaluation")
    print(f"  Source: {sample_file}")
    print(f"  Indexed: {n_chunks} chunks")
    print(f"  Queries: {len(eval_set)}")
    print(f"{'=' * 72}")

    # ── Run evaluation ────────────────────────────────────────────────────────
    reranker = Reranker()
    hit_at_1 = 0
    hit_at_3 = 0
    reciprocal_ranks = []

    print(f"\n{'#':>3}  {'BCV':>4}  {'Expected':<24s}  {'Top-1 Result':<24s}  {'Hit@1':>5}  {'Hit@3':>5}  {'RR':>6}")
    print(f"{'─'*3}  {'─'*4}  {'─'*24}  {'─'*24}  {'─'*5}  {'─'*5}  {'─'*6}")

    for i, item in enumerate(eval_set, 1):
        query = item["query"]
        expected = item["expected"]
        bcv = item["bcv"]

        # Retrieve + rerank
        candidates = indexer.hybrid_search(query, top_k=5, dense_weight=0.6)
        reranked = reranker.rerank(query, candidates, top_k=3)

        result_names = [c.function_name for c, _ in reranked]
        top1 = result_names[0] if result_names else "(none)"

        # Hit@1
        h1 = 1 if (result_names and result_names[0] == expected) else 0
        hit_at_1 += h1

        # Hit@3
        h3 = 1 if expected in result_names[:3] else 0
        hit_at_3 += h3

        # Reciprocal Rank
        rr = 0.0
        for rank, name in enumerate(result_names, 1):
            if name == expected:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        h1_mark = "  ✓" if h1 else "  ✗"
        h3_mark = "  ✓" if h3 else "  ✗"

        print(f"{i:>3}  {bcv:>4}  {expected:<24s}  {top1:<24s}  {h1_mark:>5}  {h3_mark:>5}  {rr:>6.3f}")

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    n = len(eval_set)
    mrr = sum(reciprocal_ranks) / n
    h1_rate = hit_at_1 / n
    h3_rate = hit_at_3 / n

    print(f"\n{'=' * 72}")
    print(f"  RESULTS ({n} queries against {rel_path})")
    print(f"{'─' * 72}")
    print(f"  Hit@1  :  {hit_at_1}/{n}  =  {h1_rate:.4f}  ({h1_rate*100:.1f}%)")
    print(f"  Hit@3  :  {hit_at_3}/{n}  =  {h3_rate:.4f}  ({h3_rate*100:.1f}%)")
    print(f"  MRR    :  {mrr:.4f}")
    print(f"{'─' * 72}")
    print(f"  Hit@1 = fraction of queries where the correct function is rank 1")
    print(f"  Hit@3 = fraction of queries where the correct function is in top 3")
    print(f"  MRR   = mean reciprocal rank (1/rank of first correct result)")
    print(f"{'=' * 72}")

    # ── Per-query detail (for reproducibility) ────────────────────────────────
    print(f"\n  Full query list (for reproducibility):")
    for i, item in enumerate(eval_set, 1):
        print(f"    {i:>2}. [{item['bcv']}] \"{item['query']}\"")
        print(f"        → expected: {item['expected']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
