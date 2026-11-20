from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from pgvector.sqlalchemy import Vector

from app.db import Base


class DocumentInventory(Base):
    """
    Tracks metadata and ingestion status for direct PDF files within each trial.
    The primary identity of a document inside a trial is (trial_name, relative_path).
    """
    __tablename__ = "document_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trial_name = Column(String(255), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    relative_path = Column(String(512), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    file_size = Column(BigInteger, nullable=False)
    modified_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="DISCOVERED", index=True)
    document_version = Column(Integer, nullable=False, default=1)
    parser_config = Column(JSON, nullable=True)
    embedding_model = Column(String(255), nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("trial_name", "relative_path", name="uq_trial_document_path"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "trial_name": self.trial_name,
            "filename": self.filename,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.file_size,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "status": self.status,
            "document_version": self.document_version,
            "embedding_model": self.embedding_model,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "error_code": self.error_code,
        }


class VectorVerificationRecord(Base):
    """
    Model used to directly verify persistent vector operations with pgvector (384 dimensions).
    """
    __tablename__ = "vector_verification"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trial_name = Column(String(255), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    embedding = Column(Vector(384), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PerformanceMetric(Base):
    """
    Stores technical operation timings and performance metrics.
    Strict privacy rule: NO clinical text, patient data, user questions, or LLM answers.
    Uses opaque document_id rather than clinical filenames.
    """
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trial_name = Column(String(255), nullable=False, index=True)
    document_id = Column(Integer, nullable=True, index=True)  # References DocumentInventory.id
    stage = Column(String(64), nullable=False, index=True)     # docling_parse, table_extract, ocr, chunking, embedding, pgvector_upsert, retrieval, llm_generate
    duration_ms = Column(Float, nullable=False)
    chunk_count = Column(Integer, nullable=True)
    token_count = Column(Integer, nullable=True)
    throughput_items_per_sec = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "trial_name": self.trial_name,
            "document_id": self.document_id,
            "stage": self.stage,
            "duration_ms": self.duration_ms,
            "chunk_count": self.chunk_count,
            "token_count": self.token_count,
            "throughput_items_per_sec": self.throughput_items_per_sec,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
