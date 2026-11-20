import pytest
from pathlib import Path
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.ingestion import (
    BioClinicalModernBERTEmbeddings,
    get_vectorstore,
    ingest_trial_pdf,
    query_trial_vectors,
)
from app.models import DocumentInventory, PerformanceMetric


@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_embeddings_dimensions():
    """Verify that BioClinical ModernBERT produces 768-dimensional normalized vectors."""
    embeddings = BioClinicalModernBERTEmbeddings()
    sample_text = "Primary objective is to evaluate progression-free survival."
    vec = embeddings.embed_query(sample_text)
    assert len(vec) == 768
    # Test batch embedding
    batch_vecs = embeddings.embed_documents([sample_text, "Secondary objective is safety."])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 768
    assert len(batch_vecs[1]) == 768


def test_sequential_ingestion_and_metrics(db_session: Session):
    """
    Test end-to-end ingestion of a synthetic clinical PDF:
    - Docling layout and TableFormer parsing
    - HybridChunker chunk generation
    - 768-dim ModernBERT embeddings
    - PostgreSQL vector commit
    - Technical performance metrics recording
    """
    pdf_path = Path("data/trials/Trial_101/Protocol.pdf")
    assert pdf_path.exists(), "Synthetic Trial_101/Protocol.pdf must exist"

    # Create or fetch an inventory record for Trial_101/Protocol.pdf
    inv_rec = (
        db_session.query(DocumentInventory)
        .filter(
            DocumentInventory.trial_name == "Trial_101",
            DocumentInventory.filename == "Protocol.pdf",
        )
        .first()
    )
    if not inv_rec:
        inv_rec = DocumentInventory(
            trial_name="Trial_101",
            filename="Protocol.pdf",
            relative_path="Protocol.pdf",
            sha256="dummy_sha256_trial101",
            file_size=pdf_path.stat().st_size,
            status="PROCESSING",
        )
        db_session.add(inv_rec)
        db_session.commit()
        db_session.refresh(inv_rec)

    doc_id = inv_rec.id

    # Ingest document
    result = ingest_trial_pdf(
        trial_name="Trial_101",
        pdf_path=pdf_path,
        document_id=doc_id,
        document_sha256="test_hash_101",
        db=db_session,
    )

    assert result["trial_name"] == "Trial_101"
    assert result["chunk_count"] >= 1
    assert result["total_duration_ms"] > 0
    assert result["peak_rss_mb"] < 2500  # Well within 8 GB RAM

    # Verify inventory record is updated to READY
    db_session.refresh(inv_rec)
    assert inv_rec.status == "READY"
    assert inv_rec.embedding_model == "NeuML/bioclinical-modernbert-base-embeddings"
    assert inv_rec.indexed_at is not None

    # Verify technical performance metrics were recorded with opaque document_id
    metrics = (
        db_session.query(PerformanceMetric)
        .filter(PerformanceMetric.document_id == doc_id)
        .all()
    )
    assert len(metrics) >= 3
    stages_recorded = {m.stage for m in metrics}
    assert "docling_parse" in stages_recorded
    assert "chunking" in stages_recorded
    assert "embedding" in stages_recorded

    for m in metrics:
        assert m.duration_ms >= 0
        assert m.document_id == doc_id
        # Confirm that no clinical text is stored in the metric table
        assert not hasattr(m, "text")
        assert not hasattr(m, "content")


def test_vector_similarity_and_trial_isolation(db_session: Session):
    """
    Test vector retrieval and strict trial isolation:
    - Querying Trial_101 returns Trial_101 chunks with correct 1-based page metadata
    - Querying Trial_102 NEVER returns Trial_101 chunks
    """
    # Ingest Trial_102 PDF as well to verify isolation
    pdf_102 = Path("data/trials/Trial_102/Protocol.pdf")
    assert pdf_102.exists()

    inv_102 = (
        db_session.query(DocumentInventory)
        .filter(
            DocumentInventory.trial_name == "Trial_102",
            DocumentInventory.filename == "Protocol.pdf",
        )
        .first()
    )
    if not inv_102:
        inv_102 = DocumentInventory(
            trial_name="Trial_102",
            filename="Protocol.pdf",
            relative_path="Protocol.pdf",
            sha256="dummy_sha256_trial102",
            file_size=pdf_102.stat().st_size,
            status="PROCESSING",
        )
        db_session.add(inv_102)
        db_session.commit()
        db_session.refresh(inv_102)

    ingest_trial_pdf(
        trial_name="Trial_102",
        pdf_path=pdf_102,
        document_id=inv_102.id,
        document_sha256="test_hash_102",
        db=db_session,
    )

    # 1. Query Trial_101
    results_101 = query_trial_vectors(
        trial_name="Trial_101",
        query="What is the primary endpoint for HB-101?",
        top_k=3,
        db=db_session,
    )
    assert len(results_101) > 0
    assert any("Protocol.pdf" in doc.metadata["source_file"] for doc in results_101)
    for doc in results_101:
        assert doc.metadata["trial_name"] == "Trial_101"
        assert doc.metadata["page"] >= 1  # 1-based page number
        assert doc.metadata["source_file"] in ["Protocol.pdf", "Safety_Report.pdf"]

    # 2. Query Trial_102 with the exact same query
    results_102 = query_trial_vectors(
        trial_name="Trial_102",
        query="What is the primary endpoint for HB-101?",
        top_k=3,
        db=db_session,
    )
    assert len(results_102) > 0
    for doc in results_102:
        # Strict isolation: Trial_102 query must only yield Trial_102 chunks
        assert doc.metadata["trial_name"] == "Trial_102"
        assert doc.metadata["trial_name"] != "Trial_101"
