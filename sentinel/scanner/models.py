"""Typed, serializable result models with explicit failure invariants."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """Ordered finding impact levels (most serious first)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    GAS = "gas"

    @property
    def rank(self) -> int:
        """Return a stable sorting rank."""
        return list(Severity).index(self)


class Confidence(StrEnum):
    """Confidence in the evidence, independently of impact."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScanState(StrEnum):
    """Job lifecycle and terminal engine outcomes."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPILE_ERROR = "compile_error"
    TIMEOUT = "timeout"
    ENGINE_ERROR = "engine_error"


@dataclass
class Finding:
    """One source-backed finding; ID is stable across repeated scans."""

    rule_id: str
    title: str
    severity: Severity
    confidence: Confidence
    description: str
    remediation: str
    file: str
    line_start: int
    line_end: int
    snippet: str = ""
    snippet_start: int = 1
    swc: str | None = None
    cwe: str | None = None
    provenance: list[str] = field(default_factory=lambda: ["sentinel"])
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            key = f"{self.rule_id}|{self.file}|{self.line_start}|{self.line_end}"
            self.id = hashlib.sha256(key.encode()).hexdigest()[:24]
        if self.line_start < 1 or self.line_end < self.line_start:
            raise ValueError("Invalid source range")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        """Rehydrate a stored finding with enums."""
        values = dict(data)
        values["severity"] = Severity(values["severity"])
        values["confidence"] = Confidence(values["confidence"])
        return cls(**values)


@dataclass
class ScanResult:
    """Shared web/API/CLI report, with no score allowed on failure."""

    scan_id: str
    state: ScanState
    filename: str
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: str = ""
    score: int | None = None
    grade: str | None = None
    risk: str | None = None
    breakdown: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.state != ScanState.COMPLETED and (
            self.score is not None
            or self.grade is not None
            or self.risk is not None
            or self.breakdown
        ):
            raise ValueError("Only completed scans can be scored")

    def to_dict(self) -> dict[str, Any]:
        """Serialize enums as string values using their StrEnum behavior."""
        self.__post_init__()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScanResult:
        """Rehydrate a validated persisted report."""
        values = dict(data)
        values["state"] = ScanState(values["state"])
        values["findings"] = [Finding.from_dict(f) for f in values.get("findings", [])]
        return cls(**values)
