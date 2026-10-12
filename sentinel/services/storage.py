"""Atomic SQLite job/report persistence with bounded retention."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from sentinel.scanner.models import ScanResult, ScanState


class ResultStore:
    """Store normalized reports, never raw uploaded sources."""

    def __init__(self, path: Path, retention_hours: float = 24):
        self.path = path
        self.retention = retention_hours * 3600
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL)"
            )

    def connect(self) -> sqlite3.Connection:
        """Open a short-lived connection suitable for request and worker threads."""
        return sqlite3.connect(self.path, timeout=10)

    def save(self, result: ScanResult) -> None:
        """Atomically insert/update a report while preserving its original expiry."""
        now = time.time()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO scans VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (result.scan_id, json.dumps(result.to_dict()), now, now + self.retention),
            )

    def get(self, scan_id: str) -> ScanResult | None:
        """Return a retained report; expired IDs are unavailable."""
        self.cleanup()
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM scans WHERE id=?", (scan_id,)).fetchone()
        return ScanResult.from_dict(json.loads(row[0])) if row else None

    def cleanup(self) -> int:
        """Delete expired reports, including during ordinary idle maintenance."""
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM scans WHERE expires < ?", (time.time(),))
            return cursor.rowcount

    def recover(self) -> None:
        """Mark abandoned queued/running jobs as explicit errors after restart."""
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM scans").fetchall()
        for row in rows:
            result = ScanResult.from_dict(json.loads(row[0]))
            if result.state in {ScanState.QUEUED, ScanState.RUNNING}:
                result.state = ScanState.ENGINE_ERROR
                result.diagnostics = (
                    "The application restarted before this scan completed. Please upload again."
                )
                self.save(result)
