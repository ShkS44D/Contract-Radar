"""Strict Slither envelope validation and normalized source-backed findings."""

from __future__ import annotations

from typing import Any, cast

from .compiler import CompileError
from .models import Confidence, Finding, Severity
from .source import Source

# Curated equivalences share one canonical rule and one scoring group.
EQUIVALENT_RULES = {
    "tx-origin": "SS-006",
    "unchecked-lowlevel": "SS-008",
    "suicidal": "SS-002",
    "controlled-delegatecall": "SS-007",
}
TAXONOMY = {
    "reentrancy-eth": ("107", "841"),
    "reentrancy-no-eth": ("107", "841"),
    "weak-prng": ("120", "330"),
    "arbitrary-send-eth": ("105", "284"),
    "divide-before-multiply": (None, "682"),
    "timestamp": ("116", None),
    "solc-version": ("102", None),
}
REMEDIATIONS = {
    "reentrancy-eth": "Update state before external calls (checks-effects-interactions), add a reentrancy guard, and test callback attacks.",
    "reentrancy-no-eth": "Apply checks-effects-interactions and guard external callbacks that can observe or mutate inconsistent state.",
    "weak-prng": "Use a verifiable randomness service or a tested commit-reveal scheme; do not derive randomness from manipulable block values.",
    "arbitrary-send-eth": "Authorize withdrawals explicitly and constrain the recipient and amount to recorded entitlements.",
    "divide-before-multiply": "Multiply before dividing when safe, or use a full-precision mulDiv implementation with explicit rounding and overflow tests.",
    "solc-version": "Pin a reviewed stable compiler version and check the Solidity compiler bug list for the version used to deploy.",
    "missing-zero-check": "Reject the zero address before assigning sensitive address variables.",
    "timestamp": "Avoid using block timestamps for randomness or exact-time authorization; tolerate validator-controlled timing variation.",
    "naming-convention": "Use consistent Solidity naming conventions so reviewers can distinguish contracts, functions, constants, and variables.",
    "immutable-states": "Mark constructor-only state immutable where compatible with your deployment and upgrade design.",
    "low-level-calls": "Document why a low-level call is necessary and verify its return value, target trust, and callback safety.",
}


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
        if not isinstance(elements, list) or not all(
            isinstance(element, dict) for element in elements
        ):
            raise ReportError("Missing source elements")
        location = None
        for element in sorted(elements, key=lambda e: e.get("type") != "node"):
            mapping = element.get("source_mapping", {})
            if not isinstance(mapping, dict):
                raise ReportError("Invalid source mapping")
            name = str(mapping.get("filename_relative", "")).replace("\\", "/")
            lines = mapping.get("lines", [])
            if (
                name in sources
                and isinstance(lines, list)
                and lines
                and all(isinstance(n, int) and n > 0 for n in lines)
            ):
                location = name, min(lines), max(lines)
                break
        if location is None:
            raise ReportError(f"No local source location for Slither rule {check}")
        name, start, end = location
        snippet, snippet_start = sources[name].context(start, end)
        rule_id = EQUIVALENT_RULES.get(check, f"slither/{check}")
        swc, cwe = TAXONOMY.get(check, (None, None))
        remediation = REMEDIATIONS.get(
            check,
            f"Review the affected code using Slither's {check} detector guidance: https://github.com/crytic/slither/wiki/Detector-Documentation",
        )
        if rule_id.startswith("SS-"):
            from .detectors import DETECTORS

            custom = next(detector for detector in DETECTORS if detector.id == rule_id)
            swc, cwe, remediation = custom.swc, custom.cwe, custom.remediation
        findings.append(
            Finding(
                rule_id=rule_id,
                title=check.replace("-", " ").capitalize(),
                severity=severity,
                confidence=confidence,
                description=str(detector.get("description", "")),
                remediation=remediation,
                file=name,
                line_start=start,
                line_end=end,
                snippet=snippet,
                snippet_start=snippet_start,
                provenance=["slither"],
                swc=swc,
                cwe=cwe,
            )
        )
    return findings
