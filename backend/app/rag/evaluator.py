import re
import math
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from app.rag.indexer import CodeChunk
from app.rag.citation import CitationEnforcer


@dataclass
class RAGEvalResult:
    """Heuristic evaluation metrics for a single RAG execution.

    These are lightweight term-overlap proxies, NOT RAGAS/DeepEval
    LLM-as-judge metrics. Names reflect what they actually measure.
    """
    query: str
    grounding_ratio: float        # fraction of response sentences grounded in chunk text
    retrieval_hit_rate: float     # fraction of retrieved chunks containing query terms
    ground_truth_coverage: float  # term overlap with ground truth (if provided)
    query_term_echo: float        # token overlap between query and response
    citation_compliance: float    # fraction of valid citations vs total citations
    composite_heuristic_score: float  # weighted sum of above metrics
    total_chunks_retrieved: int
    citations_stat: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RAGEvaluator:
    """Heuristic RAG Evaluation Engine.

    Measures grounding ratio, retrieval hit rate, ground truth coverage,
    query term echo, and citation compliance using term-overlap heuristics.
    These are NOT RAGAS or DeepEval metrics — no LLM-as-judge is used.
    """

    @classmethod
    def evaluate(
        cls,
        query: str,
        response: str,
        retrieved_chunks: List[CodeChunk],
        ground_truth: Optional[str] = None,
    ) -> RAGEvalResult:
        """Evaluates a RAG query/response pair using term-overlap heuristics."""
        # 1. Citation Compliance
        _, _, citation_stats = CitationEnforcer.verify_citations(response, retrieved_chunks)
        citation_compliance = citation_stats["compliance_rate"]

        # 2. Grounding Ratio (was: faithfulness)
        grounding_ratio = cls._calculate_grounding_ratio(response, retrieved_chunks)

        # 3. Retrieval Hit Rate (was: context_precision)
        retrieval_hit_rate = cls._calculate_retrieval_hit_rate(query, retrieved_chunks)

        # 4. Ground Truth Coverage (was: context_recall)
        ground_truth_coverage = cls._calculate_ground_truth_coverage(retrieved_chunks, ground_truth) if ground_truth else 1.0

        # 5. Query Term Echo (was: answer_relevance)
        query_term_echo = cls._calculate_query_term_echo(query, response)

        # Composite Heuristic Score (weighted sum, all inputs ∈ [0,1])
        composite_heuristic_score = (
            (0.30 * grounding_ratio)
            + (0.25 * citation_compliance)
            + (0.20 * retrieval_hit_rate)
            + (0.15 * query_term_echo)
            + (0.10 * ground_truth_coverage)
        )

        return RAGEvalResult(
            query=query,
            grounding_ratio=round(grounding_ratio, 4),
            retrieval_hit_rate=round(retrieval_hit_rate, 4),
            ground_truth_coverage=round(ground_truth_coverage, 4),
            query_term_echo=round(query_term_echo, 4),
            citation_compliance=round(citation_compliance, 4),
            composite_heuristic_score=round(composite_heuristic_score, 4),
            total_chunks_retrieved=len(retrieved_chunks),
            citations_stat=citation_stats,
        )

    @classmethod
    def _calculate_grounding_ratio(cls, response: str, chunks: List[CodeChunk]) -> float:
        """Fraction of response sentences whose meaningful words overlap ≥40% with chunk text.

        This is a term-overlap proxy for faithfulness — it does NOT use an LLM judge.
        """
        if not response.strip() or not chunks:
            return 0.0

        combined_chunk_text = " ".join([f"{c.file_path} {c.function_name or ''} {c.docstring or ''} {c.content}" for c in chunks]).lower()
        chunk_words = set(re.findall(r"\w+", combined_chunk_text))

        sentences = [s.strip() for s in re.split(r"[.!?]\s+", response) if len(s.strip()) > 15]
        if not sentences:
            return 1.0

        grounded_count = 0
        for sent in sentences:
            sent_words = set(re.findall(r"\w+", sent.lower()))
            # Remove common English stop words
            stop_words = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "and", "in", "for", "on", "with", "this", "that", "it"}
            meaningful_words = sent_words - stop_words
            if not meaningful_words:
                grounded_count += 1
                continue
            
            overlap = len(meaningful_words.intersection(chunk_words))
            ratio = overlap / len(meaningful_words)
            if ratio >= 0.4:
                grounded_count += 1

        return grounded_count / len(sentences)

    @classmethod
    def _calculate_retrieval_hit_rate(cls, query: str, chunks: List[CodeChunk]) -> float:
        """Fraction of retrieved chunks that contain at least one query term.

        This is a simple keyword-presence check, not a precision metric in the
        information-retrieval sense (which would require relevance labels).
        """
        if not chunks:
            return 0.0

        query_terms = set(re.findall(r"\w+", query.lower()))
        relevant_chunks = 0
        for c in chunks:
            text = f"{c.file_path} {c.function_name or ''} {c.docstring or ''} {c.content}".lower()
            if any(t in text for t in query_terms):
                relevant_chunks += 1

        return relevant_chunks / len(chunks)

    @classmethod
    def _calculate_ground_truth_coverage(cls, chunks: List[CodeChunk], ground_truth: str) -> float:
        """Fraction of ground-truth terms found in retrieved chunk text."""
        if not ground_truth or not chunks:
            return 0.0

        gt_terms = set(re.findall(r"\w+", ground_truth.lower()))
        combined_text = " ".join([c.content.lower() for c in chunks])
        retrieved_terms = set(re.findall(r"\w+", combined_text))

        overlap = len(gt_terms.intersection(retrieved_terms))
        return overlap / (len(gt_terms) or 1)

    @classmethod
    def _calculate_query_term_echo(cls, query: str, response: str) -> float:
        """Measures what fraction of query terms appear in the response, with a length bonus.

        This is NOT semantic similarity — it's literal token overlap.
        """
        if not response.strip():
            return 0.0

        query_terms = set(re.findall(r"\w+", query.lower()))
        response_terms = set(re.findall(r"\w+", response.lower()))

        overlap = len(query_terms.intersection(response_terms))
        relevance_score = overlap / (len(query_terms) or 1)

        # Scale bonus if response length is substantive (>50 words)
        length_factor = min(1.0, len(response_terms) / 30.0)
        return min(1.0, relevance_score * 0.7 + length_factor * 0.3)

    @classmethod
    def run_benchmark_suite(cls, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Runs heuristic evaluation over a list of benchmark queries."""
        results = []
        for item in dataset:
            query = item.get("query", "")
            response = item.get("response", "")
            chunks = item.get("retrieved_chunks", [])
            ground_truth = item.get("ground_truth", None)
            res = cls.evaluate(query, response, chunks, ground_truth)
            results.append(res)

        if not results:
            return {"error": "Empty dataset"}

        avg_grounding = sum(r.grounding_ratio for r in results) / len(results)
        avg_hit_rate = sum(r.retrieval_hit_rate for r in results) / len(results)
        avg_gt_coverage = sum(r.ground_truth_coverage for r in results) / len(results)
        avg_echo = sum(r.query_term_echo for r in results) / len(results)
        avg_citation = sum(r.citation_compliance for r in results) / len(results)
        avg_composite = sum(r.composite_heuristic_score for r in results) / len(results)

        return {
            "total_queries_evaluated": len(results),
            "average_grounding_ratio": round(avg_grounding, 4),
            "average_retrieval_hit_rate": round(avg_hit_rate, 4),
            "average_ground_truth_coverage": round(avg_gt_coverage, 4),
            "average_query_term_echo": round(avg_echo, 4),
            "average_citation_compliance": round(avg_citation, 4),
            "composite_heuristic_score": round(avg_composite, 4),
            "detailed_results": [r.to_dict() for r in results],
        }
