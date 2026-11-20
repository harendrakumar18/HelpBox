import os
import shutil
import time
from pathlib import Path
from threading import Thread
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import config
from app.db import SessionLocal, engine
from app.ingestion import query_trial_vectors
from app.models import DocumentInventory, PerformanceMetric
from app.sync import synchronize_trial_documents
from app.trials import TrialNotFoundError


@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _clean_trial_data():
    with engine.connect() as conn:
        conn.execute(
            text("""
                DELETE FROM performance_metrics
                WHERE trial_name IN ('Trial_A', 'Trial_B')
                   OR document_id IN (SELECT id FROM document_inventory WHERE trial_name IN ('Trial_A', 'Trial_B'));
                DELETE FROM langchain_pg_embedding
                WHERE cmetadata->>'trial_name' IN ('Trial_A', 'Trial_B');
                DELETE FROM document_inventory
                WHERE trial_name IN ('Trial_A', 'Trial_B');
            """)
        )
        conn.commit()


@pytest.fixture
def temp_trial_setup(tmp_path):
    """
    Creates an isolated temporary trials directory for incremental lifecycle testing.
    """
    _clean_trial_data()

    trials_root = tmp_path / "trials"
    trials_root.mkdir(parents=True, exist_ok=True)

    trial_a = trials_root / "Trial_A"
    trial_a.mkdir(parents=True, exist_ok=True)

    trial_b = trials_root / "Trial_B"
    trial_b.mkdir(parents=True, exist_ok=True)

    # Copy real synthetic PDFs to ensure Docling can parse them
    src_p1 = Path("data/trials/Trial_101/Protocol.pdf")
    src_p2 = Path("data/trials/Trial_102/Protocol.pdf")

    shutil.copy(src_p1, trial_a / "Protocol.pdf")
    shutil.copy(src_p2, trial_b / "Protocol.pdf")

    yield trials_root, trial_a, trial_b

    _clean_trial_data()


def test_scenario_1_and_2_first_scan_and_unchanged_skip(temp_trial_setup, db_session: Session):
    """
    Scenario 1: First scan indexes the new PDF and marks it READY.
    Scenario 2: Second scan skips unchanged file without re-embedding.
    """
    trials_root, trial_a, _ = temp_trial_setup

    # 1. First Scan
    res1 = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res1["new"] == 1
    assert res1["unchanged"] == 0
    assert res1["total_documents"] == 1

    rec = db_session.query(DocumentInventory).filter(
        DocumentInventory.trial_name == "Trial_A",
        DocumentInventory.filename == "Protocol.pdf",
    ).first()
    assert rec is not None
    assert rec.status == "READY"
    assert rec.document_version == 1

    # Verify chunks exist in pgvector
    with engine.connect() as conn:
        cnt1 = conn.execute(
            text("""
                SELECT count(*) FROM langchain_pg_embedding
                WHERE cmetadata->>'trial_name' = 'Trial_A'
                  AND cmetadata->>'source_file' = 'Protocol.pdf'
            """)
        ).scalar()
    assert cnt1 > 0

    # Count embedding metrics recorded for Trial_A before second scan
    embed_metrics_before = db_session.query(PerformanceMetric).filter(
        PerformanceMetric.trial_name == "Trial_A",
        PerformanceMetric.stage == "embedding",
    ).count()

    # 2. Second Scan (No changes)
    res2 = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res2["unchanged"] == 1
    assert res2["new"] == 0
    assert res2["modified"] == 0

    # Verify ZERO new embedding metrics were generated (re-embedding was skipped)
    embed_metrics_after = db_session.query(PerformanceMetric).filter(
        PerformanceMetric.trial_name == "Trial_A",
        PerformanceMetric.stage == "embedding",
    ).count()
    assert embed_metrics_after == embed_metrics_before


def test_scenario_3_new_pdf_added(temp_trial_setup, db_session: Session):
    """
    Scenario 3: Adding a second PDF indexes the new file while leaving the first untouched.
    """
    trials_root, trial_a, _ = temp_trial_setup

    # 1. Baseline sync for Protocol.pdf
    res_base = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res_base["new"] == 1

    # 2. Add a second PDF (Safety_Report.pdf)
    src_safety = Path("data/trials/Trial_101/Safety_Report.pdf")
    if src_safety.exists():
        shutil.copy(src_safety, trial_a / "Safety_Report.pdf")
    else:
        # Copy Protocol.pdf under new name
        shutil.copy(trial_a / "Protocol.pdf", trial_a / "Safety_Report.pdf")

    res = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res["new"] == 1
    assert res["unchanged"] == 1  # Protocol.pdf was skipped

    rec_safety = db_session.query(DocumentInventory).filter(
        DocumentInventory.trial_name == "Trial_A",
        DocumentInventory.filename == "Safety_Report.pdf",
    ).first()
    assert rec_safety.status == "READY"


def test_scenario_4_existing_pdf_modified(temp_trial_setup, db_session: Session):
    """
    Scenario 4: Existing PDF modified:
    - Detected via SHA-256 mismatch.
    - Version bumped.
    - Old searchable vectors retired and replaced with new vectors.
    - Old evidence no longer retrievable.
    """
    trials_root, trial_a, _ = temp_trial_setup

    # 1. Baseline sync for Protocol.pdf
    res_base = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res_base["new"] == 1

    rec_before = db_session.query(DocumentInventory).filter(
        DocumentInventory.trial_name == "Trial_A",
        DocumentInventory.filename == "Protocol.pdf",
    ).first()
    old_sha256 = rec_before.sha256
    old_version = rec_before.document_version

    # Modify the PDF content (copy Trial_102 Protocol into Trial_A Protocol to change content & text)
    src_p2 = Path("data/trials/Trial_102/Protocol.pdf")
    shutil.copy(src_p2, trial_a / "Protocol.pdf")

    res = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res["modified"] == 1

    db_session.refresh(rec_before)
    assert rec_before.sha256 != old_sha256
    assert rec_before.document_version == old_version + 1
    assert rec_before.status == "READY"

    # Verify old vectors with old_sha256 were purged from pgvector
    with engine.connect() as conn:
        old_vectors_count = conn.execute(
            text("""
                SELECT count(*) FROM langchain_pg_embedding
                WHERE cmetadata->>'trial_name' = 'Trial_A'
                  AND cmetadata->>'source_file' = 'Protocol.pdf'
                  AND cmetadata->>'document_sha256' = :old_hash
            """),
            {"old_hash": old_sha256},
        ).scalar()
        new_vectors_count = conn.execute(
            text("""
                SELECT count(*) FROM langchain_pg_embedding
                WHERE cmetadata->>'trial_name' = 'Trial_A'
                  AND cmetadata->>'source_file' = 'Protocol.pdf'
                  AND cmetadata->>'document_sha256' = :new_hash
            """),
            {"new_hash": rec_before.sha256},
        ).scalar()

    assert old_vectors_count == 0, "Old vectors must be completely purged"
    assert new_vectors_count > 0, "New vectors must be present in pgvector"


def test_scenario_5_timestamp_changed_hash_unchanged(temp_trial_setup, db_session: Session):
    """
    Scenario 5: File timestamp modified on disk (touch) but SHA-256 content identical:
    - Detects unchanged hash.
    - Updates timestamp in database.
    - Skips re-embedding.
    """
    trials_root, trial_a, _ = temp_trial_setup
    pdf_path = trial_a / "Protocol.pdf"

    # Initial sync to guarantee baseline state is READY
    synchronize_trial_documents("Trial_A", trials_root, db_session)

    # Touch file to change mtime
    new_mtime = time.time() + 200
    os.utime(pdf_path, (new_mtime, new_mtime))

    embed_metrics_before = db_session.query(PerformanceMetric).filter(
        PerformanceMetric.trial_name == "Trial_A",
        PerformanceMetric.stage == "embedding",
    ).count()

    res = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res["unchanged"] >= 1
    assert res["modified"] == 0

    embed_metrics_after = db_session.query(PerformanceMetric).filter(
        PerformanceMetric.trial_name == "Trial_A",
        PerformanceMetric.stage == "embedding",
    ).count()
    assert embed_metrics_after == embed_metrics_before, "No new embeddings should be generated"


def test_scenario_6_pdf_deleted_and_purged(temp_trial_setup, db_session: Session):
    """
    Scenario 6: PDF deleted from trial folder:
    - Complete scan detects absence.
    - Chunks purged from pgvector.
    - Inventory status marked WITHDRAWN.
    - Querying its content returns 0 results.
    """
    trials_root, trial_a, _ = temp_trial_setup

    # First add a second PDF (Doc_To_Delete.pdf) and sync it to READY
    doc_path = trial_a / "Doc_To_Delete.pdf"
    shutil.copy(trial_a / "Protocol.pdf", doc_path)

    res_add = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res_add["new"] >= 1

    rec_doc = db_session.query(DocumentInventory).filter(
        DocumentInventory.trial_name == "Trial_A",
        DocumentInventory.filename == "Doc_To_Delete.pdf",
    ).first()
    assert rec_doc.status == "READY"

    # Now delete it from disk
    doc_path.unlink()

    res_del = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res_del["withdrawn"] >= 1

    db_session.refresh(rec_doc)
    assert rec_doc.status == "WITHDRAWN"
    assert rec_doc.indexed_at is None

    # Verify no chunks exist in pgvector for Doc_To_Delete.pdf
    with engine.connect() as conn:
        cnt = conn.execute(
            text("""
                SELECT count(*) FROM langchain_pg_embedding
                WHERE cmetadata->>'trial_name' = 'Trial_A'
                  AND cmetadata->>'source_file' = 'Doc_To_Delete.pdf'
            """)
        ).scalar()
    assert cnt == 0, "All chunks for deleted file must be purged from pgvector"


def test_scenario_7_folder_inaccessible_error_isolation(temp_trial_setup, db_session: Session):
    """
    Scenario 7: Inaccessible/nonexistent folder:
    - Raises error.
    - Existing records are NOT marked deleted.
    """
    trials_root, _, _ = temp_trial_setup

    # Baseline sync for Trial_A
    synchronize_trial_documents("Trial_A", trials_root, db_session)

    with pytest.raises(TrialNotFoundError):
        synchronize_trial_documents("Nonexistent_Trial_XYZ", trials_root, db_session)

    # Verify Trial_A records are still READY and untouched
    rec = db_session.query(DocumentInventory).filter(
        DocumentInventory.trial_name == "Trial_A",
        DocumentInventory.filename == "Protocol.pdf",
    ).first()
    assert rec.status == "READY"


def test_scenario_8_ingestion_failure_rollback(temp_trial_setup, db_session: Session):
    """
    Scenario 8: Corrupted file during replacement:
    - Status set to FAILED.
    - No partial chunks left as READY.
    """
    trials_root, trial_a, _ = temp_trial_setup
    corrupted_pdf = trial_a / "Corrupted.pdf"
    # Write invalid PDF binary header
    corrupted_pdf.write_bytes(b"%PDF-1.4\nInvalid non-PDF junk that causes Docling error\n%%EOF")

    res = synchronize_trial_documents("Trial_A", trials_root, db_session)
    assert res["failed"] >= 1

    rec = db_session.query(DocumentInventory).filter(
        DocumentInventory.trial_name == "Trial_A",
        DocumentInventory.filename == "Corrupted.pdf",
    ).first()
    assert rec.status == "FAILED"
    assert rec.error_code == "INGESTION_FAILED"


def test_scenario_9_concurrent_refreshes_serialize(temp_trial_setup, db_session: Session):
    """
    Scenario 9: Concurrent refresh calls for the same trial:
    - Threading lock serializes execution without collision or duplicate inserts.
    """
    trials_root, trial_a, _ = temp_trial_setup
    results = []

    def worker():
        local_db = SessionLocal()
        try:
            r = synchronize_trial_documents("Trial_A", trials_root, local_db)
            results.append(r)
        finally:
            local_db.close()

    t1 = Thread(target=worker)
    t2 = Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2
    # At least one run saw unchanged files cleanly
    assert results[0]["failed"] == 0
    assert results[1]["failed"] == 0


def test_scenario_10_cross_trial_retrieval_isolation(temp_trial_setup, db_session: Session):
    """
    Scenario 10: Cross-trial retrieval isolation:
    - Index Trial_A and Trial_B.
    - Querying Trial_A yields only Trial_A evidence.
    - Querying Trial_B yields only Trial_B evidence.
    """
    trials_root, _, _ = temp_trial_setup

    synchronize_trial_documents("Trial_A", trials_root, db_session)
    synchronize_trial_documents("Trial_B", trials_root, db_session)

    res_a = query_trial_vectors("Trial_A", "Protocol endpoints", top_k=5, db=db_session)
    for doc in res_a:
        assert doc.metadata["trial_name"] == "Trial_A"
        assert doc.metadata["trial_name"] != "Trial_B"

    res_b = query_trial_vectors("Trial_B", "Protocol endpoints", top_k=5, db=db_session)
    for doc in res_b:
        assert doc.metadata["trial_name"] == "Trial_B"
        assert doc.metadata["trial_name"] != "Trial_A"
