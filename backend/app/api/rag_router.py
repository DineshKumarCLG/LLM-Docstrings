import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.rag.rag_service import rag_service
from app.rag.evaluator import RAGEvaluator

rag_api_router = APIRouter(prefix="/rag", tags=["RAG & Evaluation"])


class IndexRequest(BaseModel):
    files: Optional[Dict[str, str]] = Field(
        default=None,
        description="Dictionary mapping file paths to code contents. If None, indexes sample/local codebase files.",
    )


class QueryRequest(BaseModel):
    query: str = Field(..., description="Search query or contract verification question")
    dense_weight: float = Field(default=0.6, ge=0.0, le=1.0, description="Weight for dense vector vs sparse BM25 search")
    top_k_retrieval: int = Field(default=5, ge=1, le=20, description="Number of initial candidate chunks retrieved")
    top_k_rerank: int = Field(default=3, ge=1, le=10, description="Number of chunks after re-ranking")
    llm_provider: str = Field(default="auto", description="LLM provider: 'auto', 'openai', 'google', 'anthropic'")
    ground_truth: Optional[str] = Field(default=None, description="Optional ground truth answer for coverage evaluation")


class EvalDatasetRequest(BaseModel):
    dataset: List[Dict[str, Any]] = Field(..., description="List of query-response evaluation test items")


@rag_api_router.post("/index")
async def index_codebase(req: IndexRequest):
    """Index codebase files into the RAG vector store & BM25 keyword index."""
    try:
        files = req.files
        if not files:
            # Automatic fallback: index repository example files
            files = {}
            examples_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "examples"))
            if os.path.exists(examples_dir):
                for root, _, filenames in os.walk(examples_dir):
                    for fname in filenames:
                        if fname.endswith(".py"):
                            fpath = os.path.join(root, fname)
                            rel_path = os.path.relpath(fpath, examples_dir)
                            with open(fpath, "r", encoding="utf-8") as f:
                                files[f"examples/{rel_path}"] = f.read()

            # Include app files if examples directory empty
            if not files:
                app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                for root, _, filenames in os.walk(app_dir):
                    for fname in filenames:
                        if fname.endswith(".py"):
                            fpath = os.path.join(root, fname)
                            rel_path = os.path.relpath(fpath, app_dir)
                            with open(fpath, "r", encoding="utf-8") as f:
                                files[f"app/{rel_path}"] = f.read()

        result = rag_service.index_repository(files)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@rag_api_router.post("/query")
async def query_rag(req: QueryRequest):
    """Execute RAG search query with Re-ranking, Citation Enforcement & Heuristic Evaluation."""
    try:
        result = rag_service.execute_rag_query(
            query=req.query,
            dense_weight=req.dense_weight,
            top_k_retrieval=req.top_k_retrieval,
            top_k_rerank=req.top_k_rerank,
            llm_provider=req.llm_provider,
            ground_truth=req.ground_truth,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query execution failed: {str(e)}")


@rag_api_router.post("/eval")
async def evaluate_rag_benchmark(req: EvalDatasetRequest):
    """Run heuristic evaluation suite over a dataset of query-response pairs."""
    try:
        report = RAGEvaluator.run_benchmark_suite(req.dataset)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG evaluation suite failed: {str(e)}")


@rag_api_router.get("/stats")
async def get_rag_stats():
    """Retrieve RAG vector index statistics and heuristic evaluation history summary."""
    chunks = rag_service.indexer.chunks
    files_indexed = list(set(c.file_path for c in chunks))
    history = rag_service.evaluation_history

    avg_composite = (
        sum(h["composite_heuristic_score"] for h in history) / len(history) if history else 0.0
    )
    avg_grounding = (
        sum(h["grounding_ratio"] for h in history) / len(history) if history else 0.0
    )
    avg_citation = (
        sum(h["citation_compliance"] for h in history) / len(history) if history else 0.0
    )

    return {
        "status": "active" if chunks else "unindexed",
        "total_chunks": len(chunks),
        "files_indexed": len(files_indexed),
        "indexed_file_list": files_indexed,
        "total_queries_evaluated": len(history),
        "metrics_summary": {
            "average_composite_heuristic_score": round(avg_composite, 4),
            "average_grounding_ratio": round(avg_grounding, 4),
            "average_citation_compliance": round(avg_citation, 4),
        },
        "recent_evaluations": history[-10:],
    }
