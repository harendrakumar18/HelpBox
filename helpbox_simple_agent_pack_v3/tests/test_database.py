from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import config
from app.db import check_db_connection, init_db
from app.models import DocumentInventory, VectorVerificationRecord


@pytest.fixture(scope="module")
def db_session():
    """Create database tables and provide a clean session for testing."""
    init_db()
    engine = create_engine(config.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def test_postgres_live_connection():
    """Verify live PostgreSQL connection and pgvector extension status."""
    status = check_db_connection()
    assert status["connected"] is True
    assert "PostgreSQL" in status["postgres_version"]
    assert status["pgvector_active"] is True
    assert status["pgvector_version"] is not None


def test_document_inventory_crud(db_session):
    """Test insertion, query, update and deletion in DocumentInventory table."""
    trial_name = "Trial_Test_DB"
    filename = "Sample_Protocol.pdf"
    rel_path = "Sample_Protocol.pdf"
    doc_hash = "a" * 64
    now = datetime.now(timezone.utc)

    # Clean any prior test row
    db_session.query(DocumentInventory).filter_by(trial_name=trial_name).delete()
    db_session.commit()

    # 1. Insert
    doc = DocumentInventory(
        trial_name=trial_name,
        filename=filename,
        relative_path=rel_path,
        sha256=doc_hash,
        file_size=1024,
        modified_at=now,
        status="DISCOVERED",
        document_version=1,
    )
    db_session.add(doc)
    db_session.commit()

    assert doc.id is not None

    # 2. Query
    queried = (
        db_session.query(DocumentInventory)
        .filter_by(trial_name=trial_name, relative_path=rel_path)
        .one()
    )
    assert queried.filename == filename
    assert queried.sha256 == doc_hash
    assert queried.status == "DISCOVERED"
    assert queried.document_version == 1

    # 3. Update
    queried.status = "READY"
    queried.document_version = 2
    queried.indexed_at = datetime.now(timezone.utc)
    db_session.commit()

    updated = db_session.query(DocumentInventory).filter_by(id=queried.id).one()
    assert updated.status == "READY"
    assert updated.document_version == 2
    assert updated.indexed_at is not None

    # Cleanup
    db_session.delete(updated)
    db_session.commit()


def test_document_inventory_unique_constraint(db_session):
    """Verify that duplicate (trial_name, relative_path) violates unique constraint."""
    trial_name = "Trial_Unique_Test"
    rel_path = "Protocol.pdf"
    now = datetime.now(timezone.utc)

    db_session.query(DocumentInventory).filter_by(trial_name=trial_name).delete()
    db_session.commit()

    doc1 = DocumentInventory(
        trial_name=trial_name,
        filename="Protocol.pdf",
        relative_path=rel_path,
        sha256="1" * 64,
        file_size=2048,
        modified_at=now,
        status="DISCOVERED",
    )
    db_session.add(doc1)
    db_session.commit()

    doc2 = DocumentInventory(
        trial_name=trial_name,
        filename="Protocol.pdf",
        relative_path=rel_path,
        sha256="2" * 64,
        file_size=2048,
        modified_at=now,
        status="DISCOVERED",
    )
    db_session.add(doc2)
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()

    # Cleanup
    db_session.query(DocumentInventory).filter_by(trial_name=trial_name).delete()
    db_session.commit()


def test_pgvector_operations_and_similarity(db_session):
    """Verify storing 384-dimensional vectors and querying with cosine distance."""
    trial_name = "Trial_Vector_Test"

    db_session.query(VectorVerificationRecord).filter_by(trial_name=trial_name).delete()
    db_session.commit()

    # Vector A: [1.0, 0.0, 0.0, ...]
    vec_a = [1.0] + [0.0] * 383
    # Vector B: [0.0, 1.0, 0.0, ...]
    vec_b = [0.0, 1.0] + [0.0] * 382
    # Query vector close to A: [0.99, 0.01, 0.0, ...]
    query_vec = [0.99, 0.01] + [0.0] * 382

    rec_a = VectorVerificationRecord(trial_name=trial_name, label="Item A", embedding=vec_a)
    rec_b = VectorVerificationRecord(trial_name=trial_name, label="Item B", embedding=vec_b)

    db_session.add_all([rec_a, rec_b])
    db_session.commit()

    # Query closest item using pgvector cosine distance operator <=>
    stmt = (
        select(VectorVerificationRecord)
        .filter(VectorVerificationRecord.trial_name == trial_name)
        .order_by(VectorVerificationRecord.embedding.cosine_distance(query_vec))
        .limit(1)
    )
    closest = db_session.execute(stmt).scalar_one()
    assert closest.label == "Item A"

    # Cleanup
    db_session.query(VectorVerificationRecord).filter_by(trial_name=trial_name).delete()
    db_session.commit()


def test_data_persistence_across_connections():
    """Verify that committed data persists across distinct database engine connections."""
    trial_name = "Trial_Persistence_Test"
    rel_path = "Persistent_Doc.pdf"
    now = datetime.now(timezone.utc)

    # Connection 1: write data
    engine1 = create_engine(config.DATABASE_URL)
    Session1 = sessionmaker(bind=engine1)
    with Session1() as s1:
        s1.query(DocumentInventory).filter_by(trial_name=trial_name).delete()
        s1.commit()

        doc = DocumentInventory(
            trial_name=trial_name,
            filename=rel_path,
            relative_path=rel_path,
            sha256="c" * 64,
            file_size=5000,
            modified_at=now,
            status="READY",
            document_version=1,
        )
        s1.add(doc)
        s1.commit()
    engine1.dispose()

    # Connection 2: new engine and session, verify data survived
    engine2 = create_engine(config.DATABASE_URL)
    Session2 = sessionmaker(bind=engine2)
    with Session2() as s2:
        saved = s2.query(DocumentInventory).filter_by(trial_name=trial_name).one()
        assert saved.filename == rel_path
        assert saved.sha256 == "c" * 64
        assert saved.status == "READY"

        # Cleanup
        s2.delete(saved)
        s2.commit()
    engine2.dispose()
