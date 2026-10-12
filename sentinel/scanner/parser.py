"""Strict Slither envelope validation and normalized source-backed findings."""

from __future__ import annotations

from typing import Any, cast

from .compiler import CompileError
from .models import Confidence, Finding, Severity
from .source import Source


class ReportError(ValueError):
    """Malformed or incomplete engine output; never a clean scan."""


def validate_report(data: Any) -> list[dict[str, Any]]:
    """Require the success envelope and a detector list."""
    if not isinstance(data, dict) or not isinstance(data.get("success"), bool):
        raise ReportError("Slither report has no valid success flag")
    if not data["success"]:
        raise CompileError(str(data.get("error") or "Slither compilation failed"))
    results = data.get("results")
    if not isinstance(results, dict) or not isinstance(results.get("detectors"), list):
        raise ReportError("Slither report has no detector array")
    detectors = results["detectors"]
    if not all(isinstance(item, dict) for item in detectors):
        raise ReportError("Invalid Slither detector entry")
    return cast(list[dict[str, Any]], detectors)


def parse_report(data: Any, sources: dict[str, Source]) -> list[Finding]:
    """Convert validated Slither diagnostics, preserving relative source locations."""
    findings = []
    severity_map = {"Informational": Severity.INFO, "Optimization": Severity.GAS}
    for detector in validate_report(data):
        impact = detector.get("impact")
        if impact in severity_map:
            severity = severity_map[impact]
        else:
            try:
                severity = Severity(str(impact).lower())
            except ValueError as exc:
                raise ReportError(f"Unknown Slither impact: {impact}") from exc
        try:
            confidence = Confidence(str(detector.get("confidence")).lower())
        except ValueError as exc:
            raise ReportError("Unknown Slither confidence") from exc
        check = detector.get("check")
        if not isinstance(check, str) or not check:
            raise ReportError("Missing detector ID")
        elements = detector.get("elements")
        if not isinstance(elements, list):
            raise ReportError("Missing source elements")
        location = None
        for element in elements:
            mapping = element.get("source_mapping", {})
            name = str(mapping.get("filename_relative", "")).replace("\\", "/")
            lines = mapping.get("lines", [])
            if name in sources and lines and all(isinstance(n, int) and n > 0 for n in lines):
                location = name, min(lines), max(lines)
                break
        if location is None:
            raise ReportError(f"No local source location for Slither rule {check}")
        name, start, end = location
        snippet, snippet_start = sources[name].context(start, end)
        findings.append(
            Finding(
                rule_id=f"slither/{check}",
                title=check.replace("-", " ").capitalize(),
                severity=severity,
                confidence=confidence,
                description=str(detector.get("description", "")),
                remediation=f"Review the affected code using Slither's {check} detector guidance: https://github.com/crytic/slither/wiki/Detector-Documentation",
                file=name,
                line_start=start,
                line_end=end,
                snippet=snippet,
                snippet_start=snippet_start,
                provenance=["slither"],
            )
        )
    return findings
