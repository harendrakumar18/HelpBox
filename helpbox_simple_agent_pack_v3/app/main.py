import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import config
from app.db import check_db_connection, get_db, init_db
from app.models import DocumentInventory
from app.rag import generate_rag_answer, stream_rag_answer
from app.scanner import get_scanner
from app.sync import synchronize_trial_documents
from app.trials import (
    TrialNotFoundError,
    TrialSecurityError,
    list_trial_folders,
    list_trial_pdfs,
    sanitize_and_validate_trial_name,
)

logger = logging.getLogger("helpbox")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database tables and pgvector extension
    try:
        init_db()
        logger.info("Application startup: database initialized.")
    except Exception as e:
        logger.warning(f"Database initialization at startup deferred/warning: {e}")

    # Startup: In-process continuous background synchronization
    scanner = get_scanner()
    scanner.start()

    # Startup: Background warm-up of embedding model to eliminate first-query cold-start latency
    try:
        from app.ingestion import get_embeddings
        asyncio.create_task(asyncio.to_thread(lambda: get_embeddings().embed_query("warmup")))
        logger.info("Application startup: embedding model pre-warming initiated.")
    except Exception as e:
        logger.warning(f"Embedding warmup warning: {e}")

    yield

    # Shutdown: Stop continuous background synchronization
    await scanner.stop()
    logger.info("Application shutdown.")


app = FastAPI(
    title="Helpbox Clinical Trial PDF RAG",
    description="Trial-scoped PDF RAG assistant for clinical document Q&A",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


# Models
class DocumentInfo(BaseModel):
    filename: str
    relative_path: str
    size_bytes: int
    modified_at: str
    status: str
    sha256: Optional[str] = None
    document_version: Optional[int] = 1


class TrialListResponse(BaseModel):
    trials: List[str]


class TrialDocumentsResponse(BaseModel):
    trial_name: str
    documents: List[DocumentInfo]


class TrialStatusResponse(BaseModel):
    trial_name: str
    total_documents: int
    ready_documents: int
    status: str


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    trial_name: str
    question: str = Field(..., min_length=1)
    chat_history: Optional[List[ChatTurn]] = []


class Citation(BaseModel):
    id: int
    filename: str
    page: int
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = []
    insufficient_evidence: bool = False
    metrics: Optional[Dict[str, Any]] = None


# Endpoints
@app.get("/health")
def health_check():
    db_status = check_db_connection()
    scanner_status = get_scanner().get_status()
    return {
        "status": "ok",
        "app": "helpbox",
        "trials_dir_configured": str(config.TRIALS_DIR.name),
        "database": db_status,
        "sync": {
            "enabled": scanner_status["enabled"],
            "interval_seconds": scanner_status["interval_seconds"],
            "is_running": scanner_status["is_running"],
            "scan_count": scanner_status["scan_count"],
            "last_scan_time": scanner_status["last_scan_time"],
        },
    }


@app.get("/api/sync/status")
def get_sync_status():
    """Diagnostic endpoint reporting status of continuous document synchronization."""
    return get_scanner().get_status()


@app.post("/api/sync/run")
async def run_sync_now():
    """Trigger an immediate background scan cycle across all trial folders."""
    res = await get_scanner().trigger_scan_now()
    return {"status": "ok", "result": res}


@app.get("/api/trials", response_model=TrialListResponse)
def get_trials():
    """List available direct trial folders under configured TRIALS_DIR."""
    trials = list_trial_folders(config.TRIALS_DIR)
    return TrialListResponse(trials=trials)


@app.get("/api/trials/{trial_name}/documents", response_model=TrialDocumentsResponse)
def get_trial_documents(trial_name: str, db: Session = Depends(get_db)):
    """
    List direct PDF documents in the selected trial folder.
    Reads tracked records from PostgreSQL document inventory,
    or falls back to direct filesystem scan if not yet indexed.
    """
    try:
        # First ensure trial folder exists and is valid
        fs_docs = list_trial_pdfs(trial_name, config.TRIALS_DIR, compute_hashes=False)

        # Query database inventory
        db_records = (
            db.query(DocumentInventory)
            .filter(
                DocumentInventory.trial_name == trial_name,
                DocumentInventory.status != "WITHDRAWN",
            )
            .order_by(DocumentInventory.filename.asc())
            .all()
        )

        if db_records:
            docs = [
                DocumentInfo(
                    filename=r.filename,
                    relative_path=r.relative_path,
                    size_bytes=r.file_size,
                    modified_at=r.modified_at.isoformat(),
                    status=r.status,
                    sha256=r.sha256,
                    document_version=r.document_version,
                )
                for r in db_records
            ]
        else:
            docs = [DocumentInfo(**d) for d in fs_docs]

        return TrialDocumentsResponse(trial_name=trial_name, documents=docs)
    except TrialSecurityError as e:
        logger.warning(f"Trial security error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TrialNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/api/trials/{trial_name}/status", response_model=TrialStatusResponse)
def get_trial_status(trial_name: str, db: Session = Depends(get_db)):
    """Get document and indexing status for the selected trial from PostgreSQL."""
    try:
        # Validate trial
        list_trial_pdfs(trial_name, config.TRIALS_DIR, compute_hashes=False)

        records = (
            db.query(DocumentInventory)
            .filter(
                DocumentInventory.trial_name == trial_name,
                DocumentInventory.status != "WITHDRAWN",
            )
            .all()
        )

        if not records:
            # Check filesystem
            fs_docs = list_trial_pdfs(trial_name, config.TRIALS_DIR, compute_hashes=False)
            total = len(fs_docs)
            trial_status = "EMPTY" if total == 0 else "DISCOVERED"
            return TrialStatusResponse(
                trial_name=trial_name,
                total_documents=total,
                ready_documents=0,
                status=trial_status,
            )

        total = len(records)
        ready_count = sum(1 for r in records if r.status == "READY")
        if total == 0:
            trial_status = "EMPTY"
        elif ready_count == total:
            trial_status = "READY"
        else:
            trial_status = "DISCOVERED"

        return TrialStatusResponse(
            trial_name=trial_name,
            total_documents=total,
            ready_documents=ready_count,
            status=trial_status,
        )
    except TrialSecurityError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TrialNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/api/trials/{trial_name}/refresh", response_model=TrialDocumentsResponse)
def refresh_trial_documents(trial_name: str, db: Session = Depends(get_db)):
    """
    Incremental synchronization of direct PDFs for the selected trial:
    - Unchanged files: reused without re-embedding.
    - Timestamp-only changes: update timestamp without re-embedding.
    - New files: parsed, chunked, embedded, and marked READY.
    - Modified files: new version indexed, old vectors retired.
    - Deleted files: vectors purged from pgvector, marked WITHDRAWN.
    """
    try:
        res = synchronize_trial_documents(trial_name, config.TRIALS_DIR, db)
        docs = [DocumentInfo(**d) for d in res["documents"]]
        return TrialDocumentsResponse(trial_name=trial_name, documents=docs)
    except TrialSecurityError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TrialNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Error during refresh for {trial_name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/chat", response_model=ChatResponse)
def chat_trial(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Trial-scoped Q&A endpoint.
    Retrieves evidence exclusively from the validated trial.
    """
    try:
        sanitize_and_validate_trial_name(req.trial_name, config.TRIALS_DIR)
    except TrialSecurityError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TrialNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    chat_history_dicts = [{"role": t.role, "content": t.content} for t in (req.chat_history or [])]
    res = generate_rag_answer(
        trial_name=req.trial_name,
        question=req.question,
        db=db,
        chat_history=chat_history_dicts,
    )
    citations = [Citation(**c) for c in res["citations"]]
    return ChatResponse(
        answer=res["answer"],
        citations=citations,
        insufficient_evidence=res["insufficient_evidence"],
        metrics=res["metrics"],
    )


@app.post("/api/chat/stream")
def chat_trial_stream(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Streaming trial-scoped Q&A endpoint using Server-Sent Events (SSE).
    """
    try:
        sanitize_and_validate_trial_name(req.trial_name, config.TRIALS_DIR)
    except TrialSecurityError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TrialNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    chat_history_dicts = [{"role": t.role, "content": t.content} for t in (req.chat_history or [])]

    def event_generator():
        import json
        for event in stream_rag_answer(
            trial_name=req.trial_name,
            question=req.question,
            db=db,
            chat_history=chat_history_dicts,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Serve static frontend files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(STATIC_DIR / "index.html")
