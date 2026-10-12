"""Request-bound scanning and shared, expiring reports for Vercel Functions."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from contract_radar.config import ScannerConfig
from contract_radar.scanner.engine import scan_project
from contract_radar.scanner.models import ScanResult, ScanState

from .jobs import QueueFull

logger = logging.getLogger(__name__)


class StorageUnavailable(RuntimeError):
    """Shared storage failed; admission must fail closed."""


class RedisResultStore:
    """Keep reports private in Upstash Redis, with server-enforced TTLs."""

    def __init__(self, url: str, token: str, retention_hours: float = 24):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or not token:
            raise ValueError("Hosted scans require an HTTPS Redis REST URL and token")
        self.url = url.rstrip("/")
        self.token = token
        self.retention = retention_hours * 3600

    def command(self, *arguments: Any) -> Any:
        """Execute a bounded authenticated REST command without logging credentials."""
        request = Request(
            self.url,
            data=json.dumps(arguments).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=8) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Storage response exceeds limit")
            payload = json.loads(raw)
            if "error" in payload or "result" not in payload:
                raise ValueError("Storage command failed")
            return payload["result"]
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise StorageUnavailable("Report storage is temporarily unavailable") from exc

    def save(self, result: ScanResult) -> None:
        """Persist a bounded report without extending its original retention window."""
        submitted = float(result.metadata.setdefault("submitted_at", time.time()))
        ttl = math.ceil(submitted + self.retention - time.time())
        if ttl <= 0:
            return
        payload = json.dumps(result.to_dict())
        if len(payload.encode()) > 1_500_000:
            raise StorageUnavailable("Report exceeds hosted storage limit")
        self.command("SET", f"radar:report:{result.scan_id}", payload, "EX", ttl)

    def get(self, scan_id: str) -> ScanResult | None:
        """Read an unexpired report; Redis deletes expired keys automatically."""
        payload = self.command("GET", f"radar:report:{scan_id}")
        return ScanResult.from_dict(json.loads(payload)) if payload else None

    def admit_client(self, address: str) -> bool:
        """Apply an atomic shared ten-per-minute limit without storing raw IPs."""
        digest = hashlib.sha256(address.encode()).hexdigest()
        script = (
            "local n=redis.call('INCR',KEYS[1]); "
            "if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n"
        )
        count = self.command("EVAL", script, 1, f"radar:rate:{digest}")
        return int(count) <= 10

    def acquire(self, owner: str) -> bool:
        """Lease one global scan slot; an interrupted invocation cannot lock it forever."""
        return bool(self.command("SET", "radar:scan-slot", owner, "NX", "EX", 260) == "OK")

    def release(self, owner: str) -> None:
        """Release only the lease owned by this request."""
        script = (
            "if redis.call('GET',KEYS[1])==ARGV[1] then "
            "return redis.call('DEL',KEYS[1]) else return 0 end"
        )
        self.command("EVAL", script, 1, "radar:scan-slot", owner)


class RequestScanService:
    """Finish scans before returning, so serverless freezing cannot abandon threads."""

    def __init__(
        self,
        store: RedisResultStore,
        config: ScannerConfig,
        scan: Callable[[Path, str, str, ScannerConfig], ScanResult] = scan_project,
    ):
        self.store = store
        self.config = config
        self.scan = scan

    def submit(self, root: Path, filename: str) -> ScanResult:
        """Analyze one upload, remove its sources, then publish the terminal report."""
        scan_id = str(uuid.uuid4())
        admitted = False
        submitted = time.time()
        result = ScanResult(scan_id, ScanState.ENGINE_ERROR, filename)
        try:
            admitted = self.store.acquire(scan_id)
            if not admitted:
                raise QueueFull("The hosted scanner is busy. Please try again shortly.")
            try:
                result = self.scan(root, scan_id, filename, self.config)
            except Exception:
                logger.exception("Request-bound scanner failed")
                result.diagnostics = "The scan could not finish. Please try again."
            result.metadata["submitted_at"] = submitted
            result.metadata["execution_mode"] = "request"
        finally:
            try:
                shutil.rmtree(root)
            except OSError:
                logger.exception("Hosted source cleanup failed")
                result = ScanResult(
                    scan_id,
                    ScanState.ENGINE_ERROR,
                    filename,
                    diagnostics="Source cleanup failed. No score is available.",
                    metadata={"submitted_at": submitted},
                )
            if admitted:
                try:
                    self.store.release(scan_id)
                except StorageUnavailable:
                    logger.exception("Scan lease release failed; lease will expire")
        self.store.save(result)
        return result
