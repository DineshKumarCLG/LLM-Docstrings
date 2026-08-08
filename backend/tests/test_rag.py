import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag.indexer import ASTChunker, RAGIndexer, CodeChunk
from app.rag.reranker import Reranker
from app.rag.citation import CitationEnforcer
from app.rag.evaluator import RAGEvaluator, RAGEvalResult
from app.rag.rag_service import rag_service

client = TestClient(app)

# BCV-domain test data — actual contract violation code, not generic math
SAMPLE_BCV_CODE = '''
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


def test_ast_chunker_bcv_domain():
    """Verify AST chunker extracts all BCV sample functions."""
    chunks = ASTChunker.chunk_python_code(SAMPLE_BCV_CODE, "bcv_samples.py")
    assert len(chunks) == 4
    func_names = [c.function_name for c in chunks]
    assert "merge_dicts" in func_names
    assert "safe_divide" in func_names
    assert "flatten_nested" in func_names
    assert "normalize_list" in func_names
    # Verify docstrings extracted
    merge_chunk = next(c for c in chunks if c.function_name == "merge_dicts")
    assert "new dictionary" in merge_chunk.docstring


def test_indexer_bcv_hybrid_search():
    """Verify hybrid search retrieves correct BCV-domain chunks for contract queries."""
    indexer = RAGIndexer()
    indexed_count = indexer.index_codebase({"bcv_samples.py": SAMPLE_BCV_CODE})
    assert indexed_count == 4

    # Query about side-effect violation → should retrieve merge_dicts
    results = indexer.hybrid_search("Does merge_dicts mutate its input dictionaries?", top_k=2)
    assert len(results) > 0
    top_chunk, score = results[0]
    assert top_chunk.function_name == "merge_dicts"
    assert score > 0.0


def test_reranker_scores_bounded():
    """Verify all reranker scores are in [0, 1] — the core math fix."""
    indexer = RAGIndexer()
    indexer.index_codebase({"bcv_samples.py": SAMPLE_BCV_CODE})
    candidates = indexer.hybrid_search("normalize list side effect mutation returns", top_k=4)

    reranker = Reranker()
    reranked = reranker.rerank("normalize list side effect mutation returns", candidates, top_k=3)
    assert len(reranked) > 0
    for chunk, score in reranked:
        assert 0.0 <= score <= 1.0, f"Re-ranker score {score} out of [0,1] for chunk {chunk.function_name}"


def test_reranker_bcv_relevance():
    """Verify reranker promotes the correct BCV function for contract queries."""
    indexer = RAGIndexer()
    indexer.index_codebase({"bcv_samples.py": SAMPLE_BCV_CODE})
    candidates = indexer.hybrid_search("merge_dicts mutate input", top_k=4)

    reranker = Reranker()
    reranked = reranker.rerank("merge_dicts mutate input", candidates, top_k=1)
    assert len(reranked) == 1
    assert reranked[0][0].function_name == "merge_dicts"


def test_citation_enforcer():
    """Verify citation formatting and verification."""
    chunk = CodeChunk(
        chunk_id="bcv001",
        file_path="bcv_samples.py",
        content="def merge_dicts(base, override): base.update(override); return base",
        start_line=2,
        end_line=6,
        function_name="merge_dicts",
        docstring="Return a new dictionary containing keys from both inputs.",
    )

    prompt = CitationEnforcer.format_context_prompt("Does merge_dicts mutate input?", [chunk])
    assert "CRITICAL CITATION RULES" in prompt
    assert "[Source: bcv_samples.py:2-6 | ID: bcv001]" in prompt

    valid_response = "The function merge_dicts mutates base via update(). [Source: bcv_samples.py:2-6 | ID: bcv001]"
    processed, is_compliant, stats = CitationEnforcer.verify_citations(valid_response, [chunk])
    assert is_compliant is True
    assert stats["valid_citations"] == 1
    assert stats["compliance_rate"] == 1.0


def test_evaluator_honest_metrics():
    """Verify evaluator returns properly-named heuristic metrics, not RAGAS names."""
    chunk = CodeChunk(
        chunk_id="bcv001",
        file_path="bcv_samples.py",
        content="def merge_dicts(base, override): base.update(override); return base",
        start_line=2,
        end_line=6,
        function_name="merge_dicts",
    )

    query = "Does merge_dicts mutate its input?"
    response = "The function merge_dicts mutates the base dictionary. [Source: bcv_samples.py:2-6 | ID: bcv001]"

    eval_res = RAGEvaluator.evaluate(query, response, [chunk])
    assert isinstance(eval_res, RAGEvalResult)

    # Verify honest metric names exist
    assert hasattr(eval_res, "grounding_ratio")
    assert hasattr(eval_res, "retrieval_hit_rate")
    assert hasattr(eval_res, "ground_truth_coverage")
    assert hasattr(eval_res, "query_term_echo")
    assert hasattr(eval_res, "composite_heuristic_score")

    # Verify NO fake RAGAS names
    assert not hasattr(eval_res, "faithfulness")
    assert not hasattr(eval_res, "context_precision")
    assert not hasattr(eval_res, "context_recall")
    assert not hasattr(eval_res, "answer_relevance")
    assert not hasattr(eval_res, "overall_rag_score")

    # Verify all scores in [0, 1]
    assert 0.0 <= eval_res.grounding_ratio <= 1.0
    assert 0.0 <= eval_res.retrieval_hit_rate <= 1.0
    assert 0.0 <= eval_res.query_term_echo <= 1.0
    assert 0.0 <= eval_res.composite_heuristic_score <= 1.0
    assert eval_res.citation_compliance == 1.0
    assert eval_res.composite_heuristic_score > 0.0


def test_rag_api_endpoints():
    """Integration test: index BCV code, query, verify API response structure."""
    # 1. Index
    index_res = client.post("/api/rag/index", json={"files": {"bcv_samples.py": SAMPLE_BCV_CODE}})
    assert index_res.status_code == 200
    data = index_res.json()
    assert data["indexed_chunks"] == 4

    # 2. Query
    query_res = client.post(
        "/api/rag/query",
        json={
            "query": "Does merge_dicts mutate its input dictionaries?",
            "dense_weight": 0.6,
            "top_k_retrieval": 5,
            "top_k_rerank": 2,
        },
    )
    assert query_res.status_code == 200
    qdata = query_res.json()
    assert "answer" in qdata
    assert len(qdata["reranked_chunks"]) > 0
    assert qdata["citations"]["valid_citations"] > 0

    # Verify honest metric names in response
    eval_data = qdata["evaluation"]
    assert "composite_heuristic_score" in eval_data
    assert "grounding_ratio" in eval_data
    assert "retrieval_hit_rate" in eval_data
    assert "overall_rag_score" not in eval_data
    assert "faithfulness" not in eval_data
    assert eval_data["composite_heuristic_score"] > 0.0

    # Verify all reranked scores in [0, 1]
    for chunk in qdata["reranked_chunks"]:
        assert 0.0 <= chunk["rerank_score"] <= 1.0, f"API rerank score {chunk['rerank_score']} out of bounds"

    # 3. Stats
    stats_res = client.get("/api/rag/stats")
    assert stats_res.status_code == 200
    sdata = stats_res.json()
    assert sdata["status"] == "active"
    assert sdata["total_chunks"] == 4
    assert "average_composite_heuristic_score" in sdata["metrics_summary"]
    assert "average_grounding_ratio" in sdata["metrics_summary"]
