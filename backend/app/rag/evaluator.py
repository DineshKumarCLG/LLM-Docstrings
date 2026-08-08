import re
import math
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from app.rag.indexer import CodeChunk
from app.rag.citation import CitationEnforcer


@dataclass
class RAGEvalResult:
    """Evaluation metrics for a single RAG execution."""
    query: str
    faithfulness: float
    context_precision: float
    context_recall: float
    answer_relevance: float
    citation_compliance: float
    overall_rag_score: float
    total_chunks_retrieved: int
    citations_stat: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RAGEvaluator:
    """Automated RAG Evaluation Engine measuring Faithfulness, Precision, Recall, Relevance & Citation Compliance."""

    @classmethod
    def evaluate(
        cls,
        query: str,
        response: str,
        retrieved_chunks: List[CodeChunk],
        ground_truth: Optional[str] = None,
    ) -> RAGEvalResult:
        """Evaluates a RAG query/response pair."""
        # 1. Citation Compliance
        _, _, citation_stats = CitationEnforcer.verify_citations(response, retrieved_chunks)
        citation_compliance = citation_stats["compliance_rate"]

        # 2. Faithfulness
        faithfulness = cls._calculate_faithfulness(response, retrieved_chunks)

        # 3. Context Precision
        context_precision = cls._calculate_context_precision(query, retrieved_chunks)

        # 4. Context Recall
        context_recall = cls._calculate_context_recall(retrieved_chunks, ground_truth) if ground_truth else 1.0

        # 5. Answer Relevance
        answer_relevance = cls._calculate_answer_relevance(query, response)

        # Overall Composite Score
        overall_rag_score = (
            (0.30 * faithfulness)
            + (0.25 * citation_compliance)
            + (0.20 * context_precision)
            + (0.15 * answer_relevance)
            + (0.10 * context_recall)
        )

        return RAGEvalResult(
            query=query,
            faithfulness=round(faithfulness, 4),
            context_precision=round(context_precision, 4),
            context_recall=round(context_recall, 4),
            answer_relevance=round(answer_relevance, 4),
            citation_compliance=round(citation_compliance, 4),
            overall_rag_score=round(overall_rag_score, 4),
            total_chunks_retrieved=len(retrieved_chunks),
            citations_stat=citation_stats,
        )

    @classmethod
    def _calculate_faithfulness(cls, response: str, chunks: List[CodeChunk]) -> float:
        """Measures what fraction of factual sentences in response are grounded in chunk text."""
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
    def _calculate_context_precision(cls, query: str, chunks: List[CodeChunk]) -> float:
        """Measures the proportion of retrieved chunks relevant to query."""
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
    def _calculate_context_recall(cls, chunks: List[CodeChunk], ground_truth: str) -> float:
        """Measures ground truth overlap with retrieved context."""
        if not ground_truth or not chunks:
            return 0.0

        gt_terms = set(re.findall(r"\w+", ground_truth.lower()))
        combined_text = " ".join([c.content.lower() for c in chunks])
        retrieved_terms = set(re.findall(r"\w+", combined_text))

        overlap = len(gt_terms.intersection(retrieved_terms))
        return overlap / (len(gt_terms) or 1)

    @classmethod
    def _calculate_answer_relevance(cls, query: str, response: str) -> float:
        """Calculates token overlap and length appropriateness between query and answer."""
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
        """Runs evaluation over a list of benchmark queries."""
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

        avg_faithfulness = sum(r.faithfulness for r in results) / len(results)
        avg_precision = sum(r.context_precision for r in results) / len(results)
        avg_recall = sum(r.context_recall for r in results) / len(results)
        avg_relevance = sum(r.answer_relevance for r in results) / len(results)
        avg_citation = sum(r.citation_compliance for r in results) / len(results)
        avg_overall = sum(r.overall_rag_score for r in results) / len(results)

        return {
            "total_queries_evaluated": len(results),
            "average_faithfulness": round(avg_faithfulness, 4),
            "average_context_precision": round(avg_precision, 4),
            "average_context_recall": round(avg_recall, 4),
            "average_answer_relevance": round(avg_relevance, 4),
            "average_citation_compliance": round(avg_citation, 4),
            "overall_rag_score": round(avg_overall, 4),
            "detailed_results": [r.to_dict() for r in results],
        }
