"""Bounded background scan orchestration and source cleanup."""

from __future__ import annotations

import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
        self.config = config
        self.scan = scan
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sentinel")
        self.capacity = threading.BoundedSemaphore(workers + queue_size)
        self.store.recover()

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
        try:
            result.state = ScanState.RUNNING
            self.store.save(result)
            result = self.scan(root, result.scan_id, result.filename, self.config)
            self.store.save(result)
        except Exception:
            logger.exception("Background scan %s failed", result.scan_id)
            result = ScanResult(
                result.scan_id,
                ScanState.ENGINE_ERROR,
                result.filename,
                diagnostics="The scan could not finish. Check application logs for the error.",
            )
            self.store.save(result)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            self.capacity.release()

    def shutdown(self) -> None:
        """Wait for admitted jobs before shutting down the application."""
        self.pool.shutdown(wait=True)
