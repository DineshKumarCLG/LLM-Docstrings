import ast
import os
import re
import math
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field


@dataclass(unsafe_hash=True)
class CodeChunk:
    """Represents an AST-aware or text code chunk indexed in RAG."""
    chunk_id: str
    file_path: str
    content: str
    start_line: int
    end_line: int
    function_name: Optional[str] = None
    docstring: Optional[str] = None
    chunk_type: str = "code_block"  # 'function', 'docstring', 'module'
    metadata: Dict[str, Any] = field(default_factory=dict, hash=False)


class ASTChunker:
    """Extracts semantic, AST-aware chunks from source code."""

    @staticmethod
    def chunk_python_code(code_content: str, file_path: str) -> List[CodeChunk]:
        chunks: List[CodeChunk] = []
        lines = code_content.splitlines()

        try:
            tree = ast.parse(code_content, filename=file_path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start_line = getattr(node, "lineno", 1)
                    end_line = getattr(node, "end_lineno", len(lines))

                    func_lines = lines[start_line - 1 : end_line]
                    chunk_text = "\n".join(func_lines)
                    docstring = ast.get_docstring(node)

                    chunk_id = hashlib.md5(f"{file_path}:{start_line}:{node.name}".encode()).hexdigest()[:12]
                    chunks.append(
                        CodeChunk(
                            chunk_id=chunk_id,
                            file_path=file_path,
                            content=chunk_text,
                            start_line=start_line,
                            end_line=end_line,
                            function_name=node.name,
                            docstring=docstring,
                            chunk_type="function",
                            metadata={"args": [a.arg for a in node.args.args], "docstring": docstring or ""},
                        )
                    )
        except Exception:
            # Fallback to line block chunking if AST parsing fails or file is not valid Python AST
            pass

        if not chunks:
            # Line block chunker fallback (chunk by 25 lines with overlap)
            chunk_size = 25
            overlap = 5
            total_lines = len(lines)
            step = max(1, chunk_size - overlap)

            for i in range(0, max(1, total_lines), step):
                chunk_lines = lines[i : i + chunk_size]
                if not chunk_lines:
                    continue
                start_l = i + 1
                end_l = i + len(chunk_lines)
                chunk_text = "\n".join(chunk_lines)
                chunk_id = hashlib.md5(f"{file_path}:{start_l}:{end_l}".encode()).hexdigest()[:12]
                chunks.append(
                    CodeChunk(
                        chunk_id=chunk_id,
                        file_path=file_path,
                        content=chunk_text,
                        start_line=start_l,
                        end_line=end_l,
                        chunk_type="code_block",
                    )
                )

        return chunks


class SimpleTFIDFEmbedder:
    """Lightweight vector embedder using TF-IDF token vectors with cosine similarity fallback."""

    def __init__(self):
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}

    def fit_transform(self, documents: List[str]) -> List[List[float]]:
        tokens_per_doc = [self._tokenize(doc) for doc in documents]
        doc_count = len(documents)

        # Build vocabulary
        vocab_set = set()
        for tokens in tokens_per_doc:
            vocab_set.update(tokens)
        
        self.vocabulary = {term: idx for idx, term in enumerate(sorted(vocab_set))}
        
        # Calculate IDF
        doc_freq: Dict[str, int] = {}
        for tokens in tokens_per_doc:
            unique_tokens = set(tokens)
            for term in unique_tokens:
                doc_freq[term] = doc_freq.get(term, 0) + 1

        self.idf = {
            term: math.log((doc_count + 1) / (freq + 1)) + 1.0
            for term, freq in doc_freq.items()
        }

        return [self._transform_tokens(tokens) for tokens in tokens_per_doc]

    def transform(self, query: str) -> List[float]:
        tokens = self._tokenize(query)
        return self._transform_tokens(tokens)

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z_]\w*\b", text.lower())

    def _transform_tokens(self, tokens: List[str]) -> List[float]:
        if not self.vocabulary:
            return [0.0]

        vec = [0.0] * len(self.vocabulary)
        term_counts: Dict[str, int] = {}
        for t in tokens:
            term_counts[t] = term_counts.get(t, 0) + 1

        total_tokens = len(tokens) or 1
        for term, count in term_counts.items():
            if term in self.vocabulary:
                idx = self.vocabulary[term]
                tf = count / total_tokens
                idf = self.idf.get(term, 1.0)
                vec[idx] = tf * idf

        # Normalize L2
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class RAGIndexer:
    """Hybrid Vector + Sparse Keyword RAG Indexer."""

    def __init__(self):
        self.chunks: List[CodeChunk] = []
        self.embedder = SimpleTFIDFEmbedder()
        self.doc_vectors: List[List[float]] = []
        self.bm25_model = None

    def index_codebase(self, files_dict: Dict[str, str]) -> int:
        """Indexes dictionary of {file_path: file_content}."""
        self.chunks.clear()
        for file_path, content in files_dict.items():
            extracted = ASTChunker.chunk_python_code(content, file_path)
            self.chunks.extend(extracted)

        if not self.chunks:
            return 0

        # Build TF-IDF dense representation
        doc_texts = [f"{c.file_path} {c.function_name or ''} {c.docstring or ''} {c.content}" for c in self.chunks]
        self.doc_vectors = self.embedder.fit_transform(doc_texts)

        # Build BM25 sparse representation if rank_bm25 available
        try:
            from rank_bm25 import BM25Okapi
            tokenized_corpus = [re.findall(r"\w+", text.lower()) for text in doc_texts]
            self.bm25_model = BM25Okapi(tokenized_corpus)
        except ImportError:
            self.bm25_model = None

        return len(self.chunks)

    def search_dense(self, query: str, top_k: int = 5) -> List[Tuple[CodeChunk, float]]:
        if not self.chunks or not self.doc_vectors:
            return []

        q_vec = self.embedder.transform(query)
        scores = []
        for idx, d_vec in enumerate(self.doc_vectors):
            dot_product = sum(q * d for q, d in zip(q_vec, d_vec))
            scores.append((self.chunks[idx], dot_product))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def search_sparse(self, query: str, top_k: int = 5) -> List[Tuple[CodeChunk, float]]:
        if not self.chunks:
            return []

        query_tokens = re.findall(r"\w+", query.lower())
        if self.bm25_model is not None:
            bm25_scores = self.bm25_model.get_scores(query_tokens)
            max_score = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0
            results = [(self.chunks[i], float(bm25_scores[i] / max_score)) for i in range(len(self.chunks))]
        else:
            # Term matching fallback
            results = []
            for chunk in self.chunks:
                content_lower = chunk.content.lower()
                matched = sum(1 for t in query_tokens if t in content_lower)
                score = matched / (len(query_tokens) or 1)
                results.append((chunk, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def hybrid_search(
        self, query: str, top_k: int = 5, dense_weight: float = 0.6
    ) -> List[Tuple[CodeChunk, float]]:
        """Combines dense vector similarity and sparse BM25 scores."""
        dense_list = self.search_dense(query, top_k=top_k * 2)
        sparse_list = self.search_sparse(query, top_k=top_k * 2)

        dense_scores = {c.chunk_id: score for c, score in dense_list}
        sparse_scores = {c.chunk_id: score for c, score in sparse_list}
        chunk_map = {c.chunk_id: c for c, _ in dense_list + sparse_list}

        combined_scores: List[Tuple[CodeChunk, float]] = []

        for cid, chunk in chunk_map.items():
            d_score = dense_scores.get(cid, 0.0)
            s_score = sparse_scores.get(cid, 0.0)
            final_score = (dense_weight * d_score) + ((1.0 - dense_weight) * s_score)
            combined_scores.append((chunk, final_score))

        combined_scores.sort(key=lambda x: x[1], reverse=True)
        return combined_scores[:top_k]
