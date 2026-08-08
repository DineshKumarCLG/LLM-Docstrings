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
        """Reranks retrieved candidate chunks based on query alignment.

        Returns list of (chunk, score) tuples where score ∈ [0, 1].
        """
        if not candidate_chunks:
            return []

        chunks_only = [c for c, _ in candidate_chunks]

        # Use CrossEncoder if available — normalize raw logits to [0, 1] via min-max
        if self.cross_encoder is not None:
            try:
                pairs = [[query, f"{c.file_path} {c.function_name or ''}\n{c.content}"] for c in chunks_only]
                ce_scores = self.cross_encoder.predict(pairs)
                min_s = min(ce_scores) if len(ce_scores) > 0 else 0.0
                max_s = max(ce_scores) if len(ce_scores) > 0 else 1.0
                spread = max_s - min_s if max_s != min_s else 1.0
                normalized = [(float(s) - min_s) / spread for s in ce_scores]
                reranked = [(chunks_only[i], normalized[i]) for i in range(len(chunks_only))]
                reranked.sort(key=lambda x: x[1], reverse=True)
                return reranked[:top_k]
            except Exception:
                pass

        # Feature Scoring Engine fallback — all weights sum to 1.0, output ∈ [0, 1]
        query_terms = set(re.findall(r"\w+", query.lower()))
        contract_keywords = {"return", "returns", "raises", "raise", "param", "params", "mutates", "contract", "bcv"}

        # Weights sum to 1.0 → output guaranteed ∈ [0, 1]
        W_INITIAL = 0.30
        W_OVERLAP = 0.30
        W_SIGNATURE = 0.25
        W_CONTRACT = 0.15

        scored_chunks: List[Tuple[CodeChunk, float]] = []

        for chunk, initial_score in candidate_chunks:
            content_lower = chunk.content.lower()
            content_terms = set(re.findall(r"\w+", content_lower))

            # Component 1: Initial retrieval score, clamped to [0, 1]
            clamped_initial = max(0.0, min(1.0, initial_score))

            # Component 2: Term overlap ratio ∈ [0, 1]
            overlap_ratio = len(query_terms.intersection(content_terms)) / (len(query_terms) or 1)

            # Component 3: Signature + docstring match, blended binary ∈ [0, 1]
            sig_hit = 1.0 if (chunk.function_name and chunk.function_name.lower() in query.lower()) else 0.0
            doc_hit = 1.0 if (chunk.docstring and any(t in chunk.docstring.lower() for t in query_terms)) else 0.0
            signature_score = sig_hit * 0.6 + doc_hit * 0.4  # ∈ [0, 1]

            # Component 4: Contract keyword presence ∈ {0, 1}
            contract_score = 1.0 if any(k in content_lower for k in contract_keywords) else 0.0

            # Weighted sum — guaranteed ∈ [0, 1]
            feature_score = (
                W_INITIAL * clamped_initial
                + W_OVERLAP * overlap_ratio
                + W_SIGNATURE * signature_score
                + W_CONTRACT * contract_score
            )
            scored_chunks.append((chunk, float(feature_score)))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:top_k]
