import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app import config
from app.db import SessionLocal
from app.sync import synchronize_all_trials

logger = logging.getLogger("helpbox.scanner")


class BackgroundScanner:
    """
    In-process periodic background folder scanner for continuous document synchronization.
    Runs within FastAPI process lifespan without requiring Celery, Redis, or Kafka.

    Limitation: Runs only while the FastAPI backend service is alive.
    """

    def __init__(
        self,
        trials_dir: Optional[Path] = None,
        interval_seconds: Optional[int] = None,
        enabled: Optional[bool] = None,
        session_factory: Any = SessionLocal,
    ):
        self.trials_dir = trials_dir or config.TRIALS_DIR
        self.interval_seconds = interval_seconds if interval_seconds is not None else config.SYNC_INTERVAL_SECONDS
        self.enabled = enabled if enabled is not None else config.SYNC_ENABLED
        self.session_factory = session_factory

        self._task: Optional[asyncio.Task] = None
        self._is_running = False
        self._scan_count = 0
        self._last_scan_time: Optional[datetime] = None
        self._last_scan_duration_ms: Optional[float] = None
        self._last_scan_summary: Optional[Dict[str, Any]] = None
        self._last_error: Optional[str] = None
        self._is_scanning = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_scanning(self) -> bool:
        return self._is_scanning

    def start(self) -> bool:
        """Start the background scanner task if enabled."""
        if not self.enabled:
            logger.info("[Helpbox Background Scanner] Disabled via configuration (SYNC_ENABLED=false).")
            return False

        if self._is_running and self._task and not self._task.done():
            logger.warning("[Helpbox Background Scanner] Scanner is already running.")
            return True

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"[Helpbox Background Scanner] Started periodic scanner "
            f"(interval: {self.interval_seconds}s, root: {self.trials_dir})."
        )
        return True

    async def stop(self) -> None:
        """Stop the background scanner gracefully."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"[Helpbox Background Scanner] Error stopping task: {e}")
        logger.info("[Helpbox Background Scanner] Stopped.")

    async def trigger_scan_now(self) -> Dict[str, Any]:
        """Manually trigger an immediate scan cycle."""
        if self._is_scanning:
            return {"status": "in_progress", "detail": "Scan is already actively running."}

        return await self._execute_scan()

    async def _execute_scan(self) -> Dict[str, Any]:
        """Runs one scan cycle using a thread pool to avoid blocking async loop."""
        self._is_scanning = True
        t0 = time.perf_counter()
        try:
            summary = await asyncio.to_thread(
                synchronize_all_trials,
                self.trials_dir,
                self.session_factory,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self._scan_count += 1
            self._last_scan_time = datetime.now(timezone.utc)
            self._last_scan_duration_ms = duration_ms
            self._last_scan_summary = summary
            self._last_error = None

            print(
                f"[Helpbox Background Scanner] Cycle #{self._scan_count} complete | "
                f"Trials: {summary.get('trials_scanned', 0)} | "
                f"New: {summary.get('total_new', 0)} | "
                f"Mod: {summary.get('total_modified', 0)} | "
                f"Withdrawn: {summary.get('total_withdrawn', 0)} | "
                f"Unchanged: {summary.get('total_unchanged', 0)} | "
                f"Duration: {duration_ms:.2f}ms"
            )
            return summary
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"[Helpbox Background Scanner] Scan cycle failed: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            self._is_scanning = False

    async def _run_loop(self) -> None:
        """Main periodic loop."""
        logger.info(f"[Helpbox Background Scanner] Loop started. Initial interval: {self.interval_seconds}s")
        # Run an initial scan shortly after startup (e.g. 2 seconds after server starts)
        try:
            await asyncio.sleep(2)
            if self._is_running:
                await self._execute_scan()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[Helpbox Background Scanner] Initial startup scan failed: {e}")

        while self._is_running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._is_running:
                    break
                await self._execute_scan()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Helpbox Background Scanner] Error in loop: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of the background scanner."""
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "is_running": self._is_running,
            "is_scanning": self._is_scanning,
            "scan_count": self._scan_count,
            "last_scan_time": self._last_scan_time.isoformat() if self._last_scan_time else None,
            "last_scan_duration_ms": round(self._last_scan_duration_ms, 2) if self._last_scan_duration_ms else None,
            "last_scan_summary": self._last_scan_summary,
            "last_error": self._last_error,
        }


# Global singleton instance
_scanner_instance: Optional[BackgroundScanner] = None


def get_scanner() -> BackgroundScanner:
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = BackgroundScanner()
    return _scanner_instance
