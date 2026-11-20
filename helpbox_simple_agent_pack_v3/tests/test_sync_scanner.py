import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import config
from app.db import SessionLocal, engine, get_db
from app.main import app
from app.models import DocumentInventory
from app.scanner import BackgroundScanner, get_scanner
from app.sync import synchronize_all_trials


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides a transactional database session for tests."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provides a TestClient for FastAPI endpoints."""
    with TestClient(app) as c:
        yield c


def _clean_trial_scanner_data(trial_name: str = "Trial_ScanDemo"):
    with engine.connect() as conn:
        conn.execute(
            text("""
                DELETE FROM performance_metrics
                WHERE trial_name = :trial_name
                   OR document_id IN (SELECT id FROM document_inventory WHERE trial_name = :trial_name)
            """),
            {"trial_name": trial_name},
        )
        conn.execute(
            text("DELETE FROM langchain_pg_embedding WHERE cmetadata->>'trial_name' = :trial_name"),
            {"trial_name": trial_name},
        )
        conn.execute(
            text("DELETE FROM document_inventory WHERE trial_name = :trial_name"),
            {"trial_name": trial_name},
        )
        conn.commit()


@pytest.mark.anyio
async def test_background_scanner_lifecycle(tmp_path: Path):
    """Verify background scanner starts and stops cleanly without dangling tasks."""
    scanner = BackgroundScanner(
        trials_dir=tmp_path,
        interval_seconds=60,
        enabled=True,
        session_factory=SessionLocal,
    )
    assert not scanner.is_running
    started = scanner.start()
    assert started is True
    assert scanner.is_running is True

    # Verify status report
    status = scanner.get_status()
    assert status["enabled"] is True
    assert status["is_running"] is True
    assert status["interval_seconds"] == 60

    # Stop scanner cleanly
    await scanner.stop()
    assert scanner.is_running is False
    assert scanner.get_status()["is_running"] is False


@pytest.mark.anyio
async def test_periodic_scan_and_deletion_pruning(tmp_path: Path, db_session: Session):
    """
    Verify that synchronization:
    1. Detects and indexes newly added PDF in a trial folder.
    2. Skips unchanged files on subsequent scans.
    3. Purges vectors and marks status WITHDRAWN when the file is removed from disk.
    """
    trial_name = "Trial_ScanDemo"
    _clean_trial_scanner_data(trial_name)

    trial_dir = tmp_path / trial_name
    trial_dir.mkdir(parents=True, exist_ok=True)

    src_pdf = Path("data/trials/Trial_101/Protocol.pdf")
    assert src_pdf.exists(), "Source synthetic PDF must exist"

    dest_pdf = trial_dir / "Protocol_Scanner.pdf"
    shutil.copy(src_pdf, dest_pdf)

    scanner = BackgroundScanner(
        trials_dir=tmp_path,
        interval_seconds=120,
        enabled=True,
        session_factory=SessionLocal,
    )

    try:
        # Cycle 1: First scan indexes the new document
        res1 = await scanner.trigger_scan_now()
        assert res1["trials_scanned"] == 1
        assert res1["total_new"] == 1

        rec = (
            db_session.query(DocumentInventory)
            .filter(
                DocumentInventory.trial_name == trial_name,
                DocumentInventory.filename == "Protocol_Scanner.pdf",
            )
            .first()
        )
        assert rec is not None
        assert rec.status == "READY"
        assert rec.sha256 is not None

        # Cycle 2: Second scan skips unchanged file
        res2 = await scanner.trigger_scan_now()
        assert res2["total_unchanged"] == 1
        assert res2["total_new"] == 0

        # Cycle 3: Remove file from disk; scan must detect deletion and withdraw
        dest_pdf.unlink()
        assert not dest_pdf.exists()

        res3 = await scanner.trigger_scan_now()
        assert res3["total_withdrawn"] == 1

        db_session.refresh(rec)
        assert rec.status == "WITHDRAWN"
        assert rec.indexed_at is None

    finally:
        _clean_trial_scanner_data(trial_name)
        if trial_dir.exists():
            shutil.rmtree(trial_dir)


def test_api_sync_status_and_health(client: TestClient):
    """Verify GET /api/sync/status and /health endpoints report background sync status."""
    # Test /api/sync/status
    res = client.get("/api/sync/status")
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "is_running" in data
    assert "interval_seconds" in data
    assert data["interval_seconds"] == 120

    # Test /health
    health_res = client.get("/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert "sync" in health_data
    assert "enabled" in health_data["sync"]
    assert "interval_seconds" in health_data["sync"]
