import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle.

    Startup: pre-load the spaCy ``en_core_web_sm`` model so it's cached
    for the entire app lifetime, avoiding cold-start latency on the first
    analysis request.

    Shutdown: run any necessary cleanup.
    """
    # --- Startup ---
    # Ensure DB tables exist (safe no-op if they already do)
    from app.database import engine
    from app.models import Base
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")

    try:
        import spacy

        nlp = spacy.load("en_core_web_sm")
        app.state.spacy_nlp = nlp
        logger.info("spaCy model 'en_core_web_sm' loaded and cached")
    except Exception as exc:
        logger.warning("Failed to pre-load spaCy model: %s", exc)

    yield

    # --- Shutdown ---
    logger.info("VeriDoc shutting down — cleanup complete")


def create_app() -> FastAPI:
    """FastAPI application factory for VeriDoc.

    Creates a FastAPI instance with CORS middleware configured to allow
    requests only from the designated frontend origin (Requirement 11.5).
    Mounts the API router and configures lifecycle events.
    """
    app = FastAPI(
        title="VeriDoc",
        description=(
            "Detect Behavioral Contract Violations (BCVs) in "
            "LLM-generated Python docstrings using a three-stage "
            "pipeline: Behavioral Claim Extractor, Dynamic Test "
            "Synthesizer, and Runtime Verifier."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount the API router (all endpoints under /api)
    app.include_router(router)

    return app


app = create_app()
