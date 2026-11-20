import logging
import resource
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.ingestion import (
    get_peak_rss_mb,
    ingest_trial_pdf,
    purge_document_vectors,
    record_performance_metric,
)
from app.models import DocumentInventory
from app.trials import (
    TrialNotFoundError,
    TrialSecurityError,
    list_trial_folders,
    list_trial_pdfs,
    sanitize_and_validate_trial_name,
)

logger = logging.getLogger("helpbox.sync")

# Per-trial locks to prevent duplicate concurrent processing on the same trial
_trial_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def get_trial_lock(trial_name: str) -> threading.Lock:
    """Obtain or create a threading lock for a specific trial."""
    with _locks_guard:
        if trial_name not in _trial_locks:
            _trial_locks[trial_name] = threading.Lock()
        return _trial_locks[trial_name]


def synchronize_trial_documents(
    trial_name: str,
    trials_dir: Path,
    db: Session,
) -> Dict[str, Any]:
    """
    Synchronize direct PDFs in a trial folder with PostgreSQL inventory and pgvector store.

    Behaviors:
    1. Unchanged PDF: Identical SHA-256 and status READY -> Reuse existing vectors; zero re-embedding.
    2. Timestamp-only change: Modified timestamp changed but SHA-256 identical -> Update timestamp; zero re-embedding.
    3. New PDF: Discovered -> Process layout, chunk, embed, store vectors -> Mark READY.
    4. Modified PDF: Changed SHA-256 -> Process new version -> Verify persistence -> Retire old vectors -> Bump version -> Mark READY.
    5. Deleted PDF: Missing from complete successful scan -> Purge pgvector chunks -> Mark WITHDRAWN.
    6. Failed Scan: Inaccessible folder -> Abort without modifying inventory or marking files deleted.
    7. Concurrency: Serializes duplicate refresh attempts via per-trial lock.
    """
    t_sync_start = time.perf_counter()

    # Step 1: Validate trial name and folder safety
    trial_dir = sanitize_and_validate_trial_name(trial_name, trials_dir)
    if not trial_dir.exists() or not trial_dir.is_dir():
        raise TrialNotFoundError(f"Trial folder not found: {trial_name}")

    # Step 2: Acquire per-trial lock to protect against duplicate concurrent refreshes
    lock = get_trial_lock(trial_name)
    acquired = lock.acquire(blocking=True, timeout=60.0)
    if not acquired:
        raise RuntimeError(f"Could not acquire refresh lock for trial '{trial_name}' (timed out)")

    try:
        # Step 3: Complete scan of direct PDFs with SHA-256 hashing
        t_scan_start = time.perf_counter()
        fs_docs = list_trial_pdfs(trial_name, trials_dir, compute_hashes=True)
        scan_duration_ms = (time.perf_counter() - t_scan_start) * 1000.0

        record_performance_metric(
            db=db,
            trial_name=trial_name,
            document_id=None,
            stage="folder_scan",
            duration_ms=scan_duration_ms,
            chunk_count=len(fs_docs),
        )

        active_filenames = {d["filename"] for d in fs_docs}

        # Step 4: Load active inventory from PostgreSQL
        existing_records = (
            db.query(DocumentInventory)
            .filter(DocumentInventory.trial_name == trial_name)
            .all()
        )
        existing_by_rel_path = {r.relative_path: r for r in existing_records}

        unchanged_count = 0
        new_count = 0
        modified_count = 0
        withdrawn_count = 0
        failed_count = 0

        synced_results = []

        # Step 5: Process files found on filesystem
        for fs_doc in fs_docs:
            rel_path = fs_doc["relative_path"]
            filename = fs_doc["filename"]
            new_hash = fs_doc["sha256"]
            new_size = fs_doc["size_bytes"]
            new_mod_dt = datetime.fromisoformat(fs_doc["modified_at"])
            pdf_path = trial_dir / filename

            rec = existing_by_rel_path.get(rel_path)

            if rec is not None and rec.status == "READY" and rec.sha256 == new_hash:
                # 1. Unchanged PDF: identical hash and already READY
                unchanged_count += 1
                # If modified timestamp changed on disk (e.g. touch) but content unchanged, update timestamp
                if rec.file_size != new_size or rec.modified_at != new_mod_dt:
                    rec.file_size = new_size
                    rec.modified_at = new_mod_dt
                    db.commit()

                synced_results.append({
                    "filename": rec.filename,
                    "relative_path": rec.relative_path,
                    "size_bytes": rec.file_size,
                    "modified_at": rec.modified_at.isoformat(),
                    "status": rec.status,
                    "sha256": rec.sha256,
                    "document_version": rec.document_version,
                })
                continue

            elif rec is not None and rec.status != "WITHDRAWN" and rec.sha256 != new_hash:
                # 2. Modified PDF: SHA-256 changed
                modified_count += 1
                old_hash = rec.sha256
                rec.status = "PROCESSING"
                db.commit()

                try:
                    # Ingest new content with new SHA-256
                    ingest_trial_pdf(
                        trial_name=trial_name,
                        pdf_path=pdf_path,
                        document_id=rec.id,
                        document_sha256=new_hash,
                        db=db,
                    )
                    # Successful ingestion: retire old vectors
                    t_del_start = time.perf_counter()
                    purge_document_vectors(trial_name, filename, sha256_to_keep=new_hash)
                    del_ms = (time.perf_counter() - t_del_start) * 1000.0

                    record_performance_metric(
                        db=db,
                        trial_name=trial_name,
                        document_id=rec.id,
                        stage="vector_delete",
                        duration_ms=del_ms,
                    )

                    rec.sha256 = new_hash
                    rec.file_size = new_size
                    rec.modified_at = new_mod_dt
                    rec.document_version += 1
                    rec.status = "READY"
                    rec.indexed_at = datetime.now(timezone.utc)
                    rec.error_code = None
                    db.commit()

                    synced_results.append({
                        "filename": rec.filename,
                        "relative_path": rec.relative_path,
                        "size_bytes": rec.file_size,
                        "modified_at": rec.modified_at.isoformat(),
                        "status": rec.status,
                        "sha256": rec.sha256,
                        "document_version": rec.document_version,
                    })
                except Exception as e:
                    logger.error(f"Failed to ingest modified PDF {filename}: {e}")
                    # Ingestion failed: purge any new vectors created during failed attempt
                    purge_document_vectors(trial_name, filename, sha256_to_keep=old_hash)
                    rec.status = "FAILED"
                    rec.error_code = "UPDATE_FAILED"
                    db.commit()
                    failed_count += 1

            else:
                # 3. New PDF (or previously WITHDRAWN)
                new_count += 1
                if rec is None:
                    rec = DocumentInventory(
                        trial_name=trial_name,
                        filename=filename,
                        relative_path=rel_path,
                        sha256=new_hash,
                        file_size=new_size,
                        modified_at=new_mod_dt,
                        status="PROCESSING",
                        document_version=1,
                    )
                    db.add(rec)
                    db.commit()
                    db.refresh(rec)
                else:
                    rec.status = "PROCESSING"
                    rec.sha256 = new_hash
                    rec.file_size = new_size
                    rec.modified_at = new_mod_dt
                    rec.document_version = 1
                    db.commit()

                try:
                    ingest_trial_pdf(
                        trial_name=trial_name,
                        pdf_path=pdf_path,
                        document_id=rec.id,
                        document_sha256=new_hash,
                        db=db,
                    )
                    rec.status = "READY"
                    rec.indexed_at = datetime.now(timezone.utc)
                    rec.error_code = None
                    db.commit()

                    synced_results.append({
                        "filename": rec.filename,
                        "relative_path": rec.relative_path,
                        "size_bytes": rec.file_size,
                        "modified_at": rec.modified_at.isoformat(),
                        "status": rec.status,
                        "sha256": rec.sha256,
                        "document_version": rec.document_version,
                    })
                except Exception as e:
                    logger.error(f"Failed to ingest new PDF {filename}: {e}")
                    purge_document_vectors(trial_name, filename)
                    rec.status = "FAILED"
                    rec.error_code = "INGESTION_FAILED"
                    db.commit()
                    failed_count += 1

        # Step 6: Process deleted files (missing from successful complete scan)
        for rec in existing_records:
            if rec.filename not in active_filenames and rec.status != "WITHDRAWN":
                withdrawn_count += 1
                t_del_start = time.perf_counter()
                purge_document_vectors(trial_name, rec.filename)
                del_ms = (time.perf_counter() - t_del_start) * 1000.0

                record_performance_metric(
                    db=db,
                    trial_name=trial_name,
                    document_id=rec.id,
                    stage="vector_delete",
                    duration_ms=del_ms,
                )

                rec.status = "WITHDRAWN"
                rec.indexed_at = None
                db.commit()
                logger.info(f"[Helpbox Sync] Purged vectors for withdrawn document: {rec.filename}")

        # Step 7: Total Synchronization Metrics
        total_sync_ms = (time.perf_counter() - t_sync_start) * 1000.0
        peak_rss = get_peak_rss_mb()

        record_performance_metric(
            db=db,
            trial_name=trial_name,
            document_id=None,
            stage="total_sync",
            duration_ms=total_sync_ms,
            chunk_count=len(synced_results),
        )

        print(
            f"[Helpbox Sync] Trial: {trial_name} | Total Files: {len(fs_docs)} | "
            f"Unchanged: {unchanged_count} | New: {new_count} | Modified: {modified_count} | "
            f"Withdrawn: {withdrawn_count} | Failed: {failed_count} | "
            f"Duration: {total_sync_ms:.2f}ms | Peak RSS: {peak_rss:.1f}MB"
        )

        return {
            "trial_name": trial_name,
            "total_documents": len(synced_results),
            "unchanged": unchanged_count,
            "new": new_count,
            "modified": modified_count,
            "withdrawn": withdrawn_count,
            "failed": failed_count,
            "total_sync_ms": total_sync_ms,
            "documents": synced_results,
        }

    finally:
        lock.release()


def synchronize_all_trials(
    trials_dir: Path,
    session_factory: Any,
) -> Dict[str, Any]:
    """
    Sequentially synchronizes all direct trial folders found under trials_dir.
    Processes trials sequentially to maintain low memory profile (<1.5 GB peak RSS).
    Reusable by periodic background scanner and future company event triggers.
    """
    t_start = time.perf_counter()
    trial_names = list_trial_folders(trials_dir)
    results: Dict[str, Any] = {}
    total_unchanged = 0
    total_new = 0
    total_modified = 0
    total_withdrawn = 0
    total_failed = 0

    for trial_name in trial_names:
        db = session_factory()
        try:
            res = synchronize_trial_documents(trial_name, trials_dir, db)
            results[trial_name] = res
            total_unchanged += res.get("unchanged", 0)
            total_new += res.get("new", 0)
            total_modified += res.get("modified", 0)
            total_withdrawn += res.get("withdrawn", 0)
            total_failed += res.get("failed", 0)
        except Exception as e:
            logger.error(f"[Helpbox Sync] Error synchronizing trial '{trial_name}': {e}")
            results[trial_name] = {"error": str(e)}
            total_failed += 1
        finally:
            db.close()

    total_duration_ms = (time.perf_counter() - t_start) * 1000.0
    summary = {
        "trials_scanned": len(trial_names),
        "total_unchanged": total_unchanged,
        "total_new": total_new,
        "total_modified": total_modified,
        "total_withdrawn": total_withdrawn,
        "total_failed": total_failed,
        "total_duration_ms": round(total_duration_ms, 2),
        "trial_results": results,
    }
    return summary
