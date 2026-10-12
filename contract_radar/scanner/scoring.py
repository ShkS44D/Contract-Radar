"""Versioned observed-risk scoring with confidence and per-rule diminishing returns."""

from __future__ import annotations

import math
from collections import defaultdict

from .detectors import deduplicate
from .models import Confidence, Finding, ScanResult, ScanState, Severity

WEIGHTS = {
    Severity.CRITICAL: 35,
    Severity.HIGH: 22,
    Severity.MEDIUM: 10,
    Severity.LOW: 4,
    Severity.INFO: 0,
    Severity.GAS: 0,
}
CONFIDENCE_FACTORS = {Confidence.HIGH: 1.0, Confidence.MEDIUM: 0.75, Confidence.LOW: 0.5}
SCORING_VERSION = "1.0"


def apply_score(result: ScanResult) -> ScanResult:
    """Score a completed report in place; reject any failed/unfinished scan."""
    if result.state != ScanState.COMPLETED:
        raise ValueError("Cannot score a failed or unfinished scan")
    result.findings = deduplicate(result.findings)
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in result.findings:
        groups[finding.rule_id].append(finding)
    result.breakdown = []
    for rule, findings in sorted(groups.items()):
        weighted = sorted(
            (WEIGHTS[f.severity] * CONFIDENCE_FACTORS[f.confidence] for f in findings), reverse=True
        )
        cap = 1.5 * max(WEIGHTS[f.severity] for f in findings)
        raw = sum(value / math.sqrt(i) for i, value in enumerate(weighted, 1))
        result.breakdown.append(
            {
                "rule_id": rule,
                "instances": len(findings),
                "weighted_instances": weighted,
                "cap": cap,
                "uncapped_penalty": round(raw, 4),
                "penalty": round(min(cap, raw), 4),
            }
        )
    penalty = min(100.0, sum(float(group["penalty"]) for group in result.breakdown))
    result.score = max(0, min(100, round(100 - penalty)))
    result.grade, result.risk = next(
        (grade, risk)
        for minimum, grade, risk in [
            (90, "A", "Low"),
            (80, "B", "Moderate"),
            (70, "C", "Elevated"),
            (60, "D", "High"),
            (0, "F", "Very high"),
        ]
        if result.score >= minimum
    )
    if any(f.severity == Severity.CRITICAL for f in result.findings):
        result.risk = "Critical"
    elif result.risk not in {"High", "Very high"} and any(
        f.severity == Severity.HIGH for f in result.findings
    ):
        result.risk = "High"
    result.metadata["scoring_version"] = SCORING_VERSION
    return result
