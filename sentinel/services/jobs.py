"""Bounded background scan orchestration and source cleanup."""

from __future__ import annotations

import atexit
import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from filelock import FileLock
from filelock import Timeout as LockTimeout

from sentinel.config import ScannerConfig
from sentinel.scanner.engine import scan_project
from sentinel.scanner.models import ScanResult, ScanState

from .storage import ResultStore

logger = logging.getLogger(__name__)


class QueueFull(RuntimeError):
    """Admission capacity is exhausted; retry after a current scan finishes."""


class JobService:
    """Single-process thread pool managing isolated scanner subprocesses."""

    def __init__(
        self,
        store: ResultStore,
        config: ScannerConfig,
        workers: int = 2,
        queue_size: int = 4,
        scan: Callable[..., ScanResult] = scan_project,
    ):
        self.store = store
        self.lock = FileLock(str(store.path.parent / "worker.lock"))
        try:
            self.lock.acquire(timeout=0)
        except LockTimeout as exc:
            raise RuntimeError(
                "Only one application process may use a Sentinel data directory"
            ) from exc
        self.config = config
        self.scan = scan
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sentinel")
        self.capacity = threading.BoundedSemaphore(workers + queue_size)
        self.store.recover()
        self.temp_root = self.store.path.parent / "temp"
        if self.temp_root.exists():
            for path in self.temp_root.iterdir():
                if path.is_dir() and not path.is_symlink():
                    try:
                        uuid.UUID(path.name)
                    except ValueError:
                        continue
                    if path.resolve().parent == self.temp_root.resolve():
                        shutil.rmtree(path)
        self.stop = threading.Event()
        self.maintenance = threading.Thread(
            target=self._maintain, name="sentinel-retention", daemon=True
        )
        self.maintenance.start()
        atexit.register(self.shutdown)

    def _maintain(self) -> None:
        while not self.stop.wait(60):
            try:
                self.store.cleanup()
            except Exception:
                logger.exception("Retention cleanup failed")

    def submit(self, root: Path, filename: str) -> ScanResult:
        """Accept a prepared project, or clean it up when the queue is full."""
        if not self.capacity.acquire(blocking=False):
            shutil.rmtree(root)
            raise QueueFull("All scan slots are busy. Please try again shortly.")
        result = ScanResult(str(uuid.uuid4()), ScanState.QUEUED, filename)
        try:
            self.store.save(result)
            self.pool.submit(self._run, result, root)
        except BaseException:
            self.capacity.release()
            shutil.rmtree(root)
            raise
        return result

    def _run(self, result: ScanResult, root: Path) -> None:
        submitted = result.metadata["submitted_at"]
        try:
            result.state = ScanState.RUNNING
            self.store.save(result)
            result = self.scan(root, result.scan_id, result.filename, self.config)
            result.metadata["submitted_at"] = submitted
        except Exception:
            logger.exception("Background scan %s failed", result.scan_id)
            result = ScanResult(
                result.scan_id,
                ScanState.ENGINE_ERROR,
                result.filename,
                diagnostics="The scan could not finish. Check application logs for the error.",
                metadata={"submitted_at": submitted},
            )
        finally:
            try:
                shutil.rmtree(root)
            except OSError:
                logger.exception("Source cleanup failed for scan %s", result.scan_id)
                result = ScanResult(
                    result.scan_id,
                    ScanState.ENGINE_ERROR,
                    result.filename,
                    metadata={"submitted_at": submitted},
                    diagnostics="Source cleanup failed. Check application logs and remove retained temporary sources.",
                )
            try:
                self.store.save(result)
            finally:
                self.capacity.release()

    def shutdown(self) -> None:
        """Wait for admitted jobs before shutting down the application."""
        self.stop.set()
        self.pool.shutdown(wait=True)
        self.maintenance.join(timeout=2)
        if self.lock.is_locked:
            self.lock.release()
        atexit.unregister(self.shutdown)
