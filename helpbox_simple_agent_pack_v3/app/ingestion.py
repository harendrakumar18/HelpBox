import gc
import logging
import os
import resource
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres.vectorstores import PGVector
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine
from app.models import DocumentInventory, PerformanceMetric

logger = logging.getLogger("helpbox.ingestion")

COLLECTION_NAME = "helpbox_clinical_vectors"
EMBEDDING_MODEL_NAME = "NeuML/bioclinical-modernbert-base-embeddings"


class BioClinicalModernBERTEmbeddings(Embeddings):
    """
    BioClinical ModernBERT embedding model wrapper (768 dimensions).
    Loads model once on CPU with conservative thread management and inference_mode.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME, device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._warmed_up = False

    @property
    def model(self):
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            # Set conservative PyTorch CPU thread count to eliminate thread contention
            threads = int(os.getenv("TORCH_NUM_THREADS", "2"))
            torch.set_num_threads(threads)

            t0 = time.perf_counter()
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._model.eval()
            t1 = time.perf_counter()
            logger.info(f"Loaded embedding model {self.model_name} (threads={threads}) in {(t1-t0)*1000:.1f}ms")
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        import torch

        with torch.inference_mode():
            embeddings = self.model.encode(
                texts,
                batch_size=4,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        import torch

        with torch.inference_mode():
            embedding = self.model.encode(
                text,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
        return embedding.tolist()

    def warmup(self) -> float:
        """Run single inference query to pre-load PyTorch graphs during server startup."""
        if not self._warmed_up:
            t0 = time.perf_counter()
            self.embed_query("Clinical protocol warmup query.")
            self._warmed_up = True
            dur_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(f"Embedding model pre-warmed in {dur_ms:.1f}ms")
            return dur_ms
        return 0.0


_embeddings_instance: Optional[BioClinicalModernBERTEmbeddings] = None


def get_embeddings() -> BioClinicalModernBERTEmbeddings:
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = BioClinicalModernBERTEmbeddings()
    return _embeddings_instance


def ensure_fts_index() -> None:
    """Ensures PostgreSQL Full-Text Search GIN index exists on langchain_pg_embedding."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_fts 
                ON langchain_pg_embedding 
                USING gin(to_tsvector('english', document));
            """))
            conn.commit()
    except Exception as e:
        logger.warning(f"Could not verify/create FTS GIN index: {e}")


def get_vectorstore() -> PGVector:
    """Return LangChain PGVector instance for 768-dim clinical vectors."""
    vs = PGVector(
        embeddings=get_embeddings(),
        collection_name=COLLECTION_NAME,
        connection=engine,
        use_jsonb=True,
    )
    vs.create_tables_if_not_exists()
    ensure_fts_index()
    return vs


def get_peak_rss_mb() -> float:
    """Return peak resident memory usage in megabytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def record_performance_metric(
    db: Optional[Session],
    trial_name: str,
    document_id: Optional[int],
    stage: str,
    duration_ms: float,
    chunk_count: Optional[int] = None,
    token_count: Optional[int] = None,
    throughput_items_per_sec: Optional[float] = None,
) -> None:
    """
    Safely record technical performance metrics in PostgreSQL.
    Strict privacy rule: NO clinical text, patient data, questions, or answers.
    Uses opaque document_id rather than filenames.
    """
    if db is None:
        return
    try:
        metric = PerformanceMetric(
            trial_name=trial_name,
            document_id=document_id,
            stage=stage,
            duration_ms=round(duration_ms, 2),
            chunk_count=chunk_count,
            token_count=token_count,
            throughput_items_per_sec=round(throughput_items_per_sec, 2) if throughput_items_per_sec else None,
        )
        db.add(metric)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to record performance metric for stage {stage}: {e}")
        db.rollback()


def ingest_trial_pdf(
    trial_name: str,
    pdf_path: Path,
    document_id: Optional[int] = None,
    document_sha256: Optional[str] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Ingest a single clinical PDF file sequentially:
    1. Docling layout and reading order extraction with TableFormer.
    2. Docling HybridChunker structure-aware tokenization.
    3. BioClinical ModernBERT 768-dim embedding generation.
    4. PGVectorStore insertion with trial-scoped metadata.
    5. Detailed time.perf_counter() instrumentation and logging.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    filename = pdf_path.name
    t_start = time.perf_counter()
    logger.info(f"[Helpbox Ingest] Starting sequential ingestion for {trial_name} / {filename}")

    # Stage 1: Docling Document Layout Parsing & TableFormer
    t_parse_start = time.perf_counter()
    pipeline_opts = PdfPipelineOptions()
    pipeline_opts.table_structure_options.mode = TableFormerMode.FAST
    pipeline_opts.do_ocr = True  # OcrAutoOptions: only OCRs if text is missing

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)}
    )
    conv_res = converter.convert(pdf_path)
    t_parse_end = time.perf_counter()
    duration_parse_ms = (t_parse_end - t_parse_start) * 1000.0

    doc = conv_res.document
    page_count = len(doc.pages) if hasattr(doc, "pages") and doc.pages else 1
    table_count = len(doc.tables) if hasattr(doc, "tables") and doc.tables else 0

    # Stage 2: Table extraction duration
    t_table_start = time.perf_counter()
    # TableFormer structures are already generated during conversion; record extraction metric
    duration_table_ms = (time.perf_counter() - t_table_start) * 1000.0

    # Stage 3: Structure-Aware Chunking (HybridChunker, max_tokens=800)
    t_chunk_start = time.perf_counter()
    chunker = HybridChunker(max_tokens=800)
    raw_chunks = list(chunker.chunk(doc))
    duration_chunk_ms = (time.perf_counter() - t_chunk_start) * 1000.0
    chunk_count = len(raw_chunks)

    # Decouple Docling parser memory before embedding
    del doc
    del conv_res
    del converter
    gc.collect()

    # Convert chunks to LangChain Document objects with normalized metadata
    documents: List[Document] = []
    total_tokens_approx = 0

    for idx, ch in enumerate(raw_chunks):
        # Extract 1-based page numbers from provenance (DOCX defaults to 1)
        pages = set()
        for item in ch.meta.doc_items:
            if hasattr(item, "prov") and item.prov:
                for p in item.prov:
                    if hasattr(p, "page_no"):
                        pages.add(p.page_no)
        # Default to page 1 if provenance is empty (e.g. DOCX documents)
        primary_page = min(pages) if pages else 1
        heading_context = " > ".join(ch.meta.headings) if ch.meta.headings else ""

        element_type = "table" if any("table" in str(getattr(it, "label", "")).lower() for it in ch.meta.doc_items) else "text"
        token_count = len(ch.text.split()) * 4 // 3  # Approximate tokens
        total_tokens_approx += token_count

        metadata = {
            "trial_name": trial_name,
            "source_file": filename,
            "relative_path": filename,
            "page": primary_page,
            "document_sha256": document_sha256 or "",
            "chunk_id": idx,
            "element_type": element_type,
            "heading": heading_context,
        }
        documents.append(Document(page_content=ch.text, metadata=metadata))

    # Stage 4: Embedding Generation & pgvector Upsert
    t_embed_start = time.perf_counter()
    vectorstore = get_vectorstore()
    # Purge any existing vectors for this document to prevent duplicate chunk accumulation
    purge_document_vectors(trial_name=trial_name, filename=filename)
    vectorstore.add_documents(documents)
    t_embed_end = time.perf_counter()
    duration_embed_ms = (t_embed_end - t_embed_start) * 1000.0

    embedding_throughput = (chunk_count / (duration_embed_ms / 1000.0)) if duration_embed_ms > 0 else 0.0

    t_total_end = time.perf_counter()
    total_duration_ms = (t_total_end - t_start) * 1000.0
    peak_rss = get_peak_rss_mb()

    # Console Observability Log
    print(
        f"[Helpbox Ingest] Trial: {trial_name} | DocID: {document_id or 'N/A'} | File: {filename}\n"
        f"  - Docling Layout Parse:      {duration_parse_ms:8.2f} ms ({page_count} pages)\n"
        f"  - TableFormer Tables:        {duration_table_ms:8.2f} ms ({table_count} tables detected)\n"
        f"  - HybridChunker (800 tok):   {duration_chunk_ms:8.2f} ms ({chunk_count} chunks produced)\n"
        f"  - ModernBERT Embed & Commit: {duration_embed_ms:8.2f} ms (throughput: {embedding_throughput:5.1f} chunks/sec)\n"
        f"  - Total Ingestion Duration:  {total_duration_ms:8.2f} ms\n"
        f"  - Peak RSS Memory:           {peak_rss:8.1f} MB"
    )

    # Persist Technical Metrics to PostgreSQL (Zero clinical text stored)
    if db and document_id:
        record_performance_metric(
            db=db,
            trial_name=trial_name,
            document_id=document_id,
            stage="docling_parse",
            duration_ms=duration_parse_ms,
            token_count=total_tokens_approx,
        )
        record_performance_metric(
            db=db,
            trial_name=trial_name,
            document_id=document_id,
            stage="table_extract",
            duration_ms=duration_table_ms,
            chunk_count=table_count,
        )
        record_performance_metric(
            db=db,
            trial_name=trial_name,
            document_id=document_id,
            stage="chunking",
            duration_ms=duration_chunk_ms,
            chunk_count=chunk_count,
        )
        record_performance_metric(
            db=db,
            trial_name=trial_name,
            document_id=document_id,
            stage="embedding",
            duration_ms=duration_embed_ms,
            chunk_count=chunk_count,
            token_count=total_tokens_approx,
            throughput_items_per_sec=embedding_throughput,
        )

        # Update DocumentInventory record to READY
        try:
            inv = db.query(DocumentInventory).filter(DocumentInventory.id == document_id).first()
            if inv:
                inv.status = "READY"
                inv.embedding_model = EMBEDDING_MODEL_NAME
                inv.indexed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update document inventory status: {e}")
            db.rollback()

    return {
        "trial_name": trial_name,
        "filename": filename,
        "document_id": document_id,
        "page_count": page_count,
        "table_count": table_count,
        "chunk_count": chunk_count,
        "total_duration_ms": total_duration_ms,
        "throughput_chunks_per_sec": embedding_throughput,
        "peak_rss_mb": peak_rss,
    }


def purge_document_vectors(
    trial_name: str,
    filename: str,
    sha256_to_keep: Optional[str] = None,
) -> int:
    """
    Remove vectors for a document from langchain_pg_embedding.
    If sha256_to_keep is provided, purges only old vectors whose document_sha256 != sha256_to_keep.
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        if sha256_to_keep:
            stmt = text("""
                DELETE FROM langchain_pg_embedding
                WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = :collection_name)
                  AND cmetadata->>'trial_name' = :trial_name
                  AND cmetadata->>'source_file' = :filename
                  AND (cmetadata->>'document_sha256' IS NULL OR cmetadata->>'document_sha256' != :keep_sha256);
            """)
            res = conn.execute(
                stmt,
                {
                    "collection_name": COLLECTION_NAME,
                    "trial_name": trial_name,
                    "filename": filename,
                    "keep_sha256": sha256_to_keep,
                },
            )
        else:
            stmt = text("""
                DELETE FROM langchain_pg_embedding
                WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = :collection_name)
                  AND cmetadata->>'trial_name' = :trial_name
                  AND cmetadata->>'source_file' = :filename;
            """)
            res = conn.execute(
                stmt,
                {
                    "collection_name": COLLECTION_NAME,
                    "trial_name": trial_name,
                    "filename": filename,
                },
            )
        conn.commit()
        return res.rowcount


def query_trial_vectors(
    trial_name: str,
    query: str,
    top_k: int = 4,
    db: Optional[Session] = None,
    return_metrics: bool = False,
):
    """
    Query trial-isolated vectors from helpbox_clinical_vectors using PostgreSQL Hybrid Retrieval.
    Combines dense semantic search (pgvector cosine distance) with sparse keyword search
    (PostgreSQL Full-Text Search tsvector/tsquery) via Reciprocal Rank Fusion (RRF).
    Filters server-side strictly by trial_name metadata.
    Records retrieval latency in performance_metrics.
    """
    t_emb_start = time.perf_counter()
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(query)
    query_embedding_ms = (time.perf_counter() - t_emb_start) * 1000.0

    t_search_start = time.perf_counter()
    vectorstore = get_vectorstore()

    # 1. Dense retrieval (pgvector cosine distance)
    dense_docs = vectorstore.similarity_search_by_vector(
        embedding=query_vector,
        k=top_k * 2,
        filter={"trial_name": trial_name},
    )

    # 2. Sparse full-text search (PostgreSQL FTS)
    fts_docs = []
    try:
        with engine.connect() as conn:
            stmt = text("""
                SELECT id, document, cmetadata,
                       ts_rank_cd(to_tsvector('english', document), plainto_tsquery('english', :q)) AS rank
                FROM langchain_pg_embedding
                WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = :collection_name)
                  AND cmetadata->>'trial_name' = :trial_name
                  AND to_tsvector('english', document) @@ plainto_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT :limit;
            """)
            rows = conn.execute(stmt, {
                "collection_name": COLLECTION_NAME,
                "trial_name": trial_name,
                "q": query,
                "limit": top_k * 2,
            }).fetchall()
            for r in rows:
                fts_docs.append(Document(page_content=r[1], metadata=r[2]))
    except Exception as e:
        logger.warning(f"FTS search encountered error, falling back to dense-only: {e}")

    # 3. Reciprocal Rank Fusion (RRF)
    if fts_docs:
        rrf_scores = {}
        doc_map = {}
        k_rrf = 60
        for rank, doc in enumerate(dense_docs, start=1):
            key = (
                doc.metadata.get("source_file"),
                doc.metadata.get("page"),
                doc.metadata.get("chunk_id"),
                doc.page_content,
            )
            doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k_rrf + rank))

        for rank, doc in enumerate(fts_docs, start=1):
            key = (
                doc.metadata.get("source_file"),
                doc.metadata.get("page"),
                doc.metadata.get("chunk_id"),
                doc.page_content,
            )
            doc_map[key] = doc
            # Give exact keyword/metric hits slightly higher weight (1.2x)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.2 / (k_rrf + rank))

        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        results = [doc_map[k] for k in sorted_keys[:top_k]]
    else:
        results = dense_docs[:top_k]

    vector_search_ms = (time.perf_counter() - t_search_start) * 1000.0
    total_retrieval_ms = query_embedding_ms + vector_search_ms

    logger.info(
        f"[Helpbox Retrieval] Query: '{query[:40]}...' | Trial: {trial_name} | "
        f"Results: {len(results)} (Dense: {len(dense_docs)}, FTS: {len(fts_docs)}) | "
        f"Embed: {query_embedding_ms:.2f}ms | Search: {vector_search_ms:.2f}ms | Total: {total_retrieval_ms:.2f}ms"
    )

    if db:
        record_performance_metric(
            db=db,
            trial_name=trial_name,
            document_id=None,
            stage="retrieval",
            duration_ms=total_retrieval_ms,
            chunk_count=len(results),
        )

    metrics = {
        "query_embedding_ms": round(query_embedding_ms, 2),
        "vector_search_ms": round(vector_search_ms, 2),
        "retrieval_ms": round(total_retrieval_ms, 2),
    }

    if return_metrics:
        return results, metrics
    return results
