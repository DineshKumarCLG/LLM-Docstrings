import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag.indexer import ASTChunker, RAGIndexer, CodeChunk
from app.rag.reranker import Reranker
from app.rag.citation import CitationEnforcer
from app.rag.evaluator import RAGEvaluator, RAGEvalResult
from app.rag.rag_service import rag_service

client = TestClient(app)

SAMPLE_CODE = '''
def normalize_list(data: list[float]) -> list[float]:
    """Returns a new list with values scaled to [0, 1].
    Does not modify the input list.
    """
    min_val, max_val = min(data), max(data)
    for i in range(len(data)):
        data[i] = (data[i] - min_val) / (max_val - min_val)
    return data

def compute_factorial(n: int) -> int:
    """Computes factorial of a non-negative integer.
    Raises ValueError if n is negative.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return 1
    return n * compute_factorial(n - 1)
'''


def test_ast_chunker():
    chunks = ASTChunker.chunk_python_code(SAMPLE_CODE, "sample.py")
    assert len(chunks) == 2
    assert chunks[0].function_name == "normalize_list"
    assert "scaled to [0, 1]" in chunks[0].docstring
    assert chunks[1].function_name == "compute_factorial"


def test_indexer_hybrid_search():
    indexer = RAGIndexer()
    indexed_count = indexer.index_codebase({"sample.py": SAMPLE_CODE})
    assert indexed_count == 2

    # Query for factorial exception
    results = indexer.hybrid_search("factorial ValueError exception", top_k=2)
    assert len(results) > 0
    top_chunk, score = results[0]
    assert top_chunk.function_name == "compute_factorial"
    assert score > 0.0


def test_reranker():
    indexer = RAGIndexer()
    indexer.index_codebase({"sample.py": SAMPLE_CODE})
    candidates = indexer.hybrid_search("normalize list scaled", top_k=2)

    reranker = Reranker()
    reranked = reranker.rerank("normalize list scaled", candidates, top_k=1)
    assert len(reranked) == 1
    assert reranked[0][0].function_name == "normalize_list"


def test_citation_enforcer():
    chunk = CodeChunk(
        chunk_id="chk123",
        file_path="sample.py",
        content="def foo(): return 42",
        start_line=1,
        end_line=5,
        function_name="foo",
    )

    prompt = CitationEnforcer.format_context_prompt("How does foo work?", [chunk])
    assert "CRITICAL CITATION RULES" in prompt
    assert "[Source: sample.py:1-5 | ID: chk123]" in prompt

    valid_response = "The function foo returns 42. [Source: sample.py:1-5 | ID: chk123]"
    processed, is_compliant, stats = CitationEnforcer.verify_citations(valid_response, [chunk])
    assert is_compliant is True
    assert stats["valid_citations"] == 1
    assert stats["compliance_rate"] == 1.0


def test_rag_evaluator():
    chunk = CodeChunk(
        chunk_id="chk123",
        file_path="sample.py",
        content="def normalize_list(data): return data",
        start_line=1,
        end_line=10,
        function_name="normalize_list",
    )

    query = "Does normalize_list modify input?"
    response = "The function normalize_list modifies the list. [Source: sample.py:1-10 | ID: chk123]"

    eval_res = RAGEvaluator.evaluate(query, response, [chunk])
    assert isinstance(eval_res, RAGEvalResult)
    assert eval_res.faithfulness >= 0.0
    assert eval_res.citation_compliance == 1.0
    assert eval_res.overall_rag_score > 0.0


def test_rag_api_endpoints():
    # 1. Index
    index_res = client.post("/api/rag/index", json={"files": {"sample.py": SAMPLE_CODE}})
    assert index_res.status_code == 200
    data = index_res.json()
    assert data["indexed_chunks"] == 2

    # 2. Query
    query_res = client.post(
        "/api/rag/query",
        json={
            "query": "Is there a side effect in normalize_list?",
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
    assert qdata["evaluation"]["overall_rag_score"] > 0.0

    # 3. Stats
    stats_res = client.get("/api/rag/stats")
    assert stats_res.status_code == 200
    sdata = stats_res.json()
    assert sdata["status"] == "active"
    assert sdata["total_chunks"] == 2
