import re
from typing import List, Tuple, Optional
from app.rag.indexer import CodeChunk


class Reranker:
    """Hybrid Cross-Encoder and Multi-Attribute Feature Reranker."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.cross_encoder = None
        self._load_model_silent()

    def _load_model_silent(self):
        try:
            from sentence_transformers import CrossEncoder
            self.cross_encoder = CrossEncoder(self.model_name)
        except Exception:
            self.cross_encoder = None

    def rerank(
        self, query: str, candidate_chunks: List[Tuple[CodeChunk, float]], top_k: int = 3
    ) -> List[Tuple[CodeChunk, float]]:
        """Reranks retrieved candidate chunks based on query alignment."""
        if not candidate_chunks:
            return []

        chunks_only = [c for c, _ in candidate_chunks]

        # Use CrossEncoder if available
        if self.cross_encoder is not None:
            try:
                pairs = [[query, f"{c.file_path} {c.function_name or ''}\n{c.content}"] for c in chunks_only]
                ce_scores = self.cross_encoder.predict(pairs)
                reranked = [(chunks_only[i], float(ce_scores[i])) for i in range(len(chunks_only))]
                reranked.sort(key=lambda x: x[1], reverse=True)
                return reranked[:top_k]
            except Exception:
                pass

        # Feature Scoring Engine fallback
        query_terms = set(re.findall(r"\w+", query.lower()))
        contract_keywords = {"return", "returns", "raises", "raise", "param", "params", "mutates", "contract", "bcv"}

        scored_chunks: List[Tuple[CodeChunk, float]] = []

        for chunk, initial_score in candidate_chunks:
            content_lower = chunk.content.lower()
            content_terms = set(re.findall(r"\w+", content_lower))

            # 1. Term overlap ratio
            overlap_ratio = len(query_terms.intersection(content_terms)) / (len(query_terms) or 1)

            # 2. Signature & docstring bonus
            sig_bonus = 0.0
            if chunk.function_name and chunk.function_name.lower() in query.lower():
                sig_bonus += 0.35
            if chunk.docstring and any(t in chunk.docstring.lower() for t in query_terms):
                sig_bonus += 0.25

            # 3. Behavioral Contract keyword match
            contract_bonus = 0.2 if any(k in content_lower for k in contract_keywords) else 0.0

            # Combined score calculation
            feature_score = (0.35 * initial_score) + (0.35 * overlap_ratio) + sig_bonus + contract_bonus
            scored_chunks.append((chunk, float(feature_score)))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:top_k]
