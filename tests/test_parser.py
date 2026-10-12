"""Normalize engine fixtures without losing evidence or silently accepting schema drift."""

import json
from pathlib import Path

import pytest

from contract_radar.scanner.models import Finding, Severity
from contract_radar.scanner.parser import ReportError, parse_report
from contract_radar.scanner.source import Source


def fixture():
    return json.loads((Path(__file__).parent / "fixtures/slither.json").read_text())


def test_parser_fixture():
    findings = parse_report(
        fixture(),
        {
            "A.sol": Source(
                "A.sol", "contract A {\nfunction f() public {\nrequire(tx.origin == owner);\n}\n}"
            )
        },
    )
    assert findings[0].rule_id == "SS-006" and findings[0].line_start == 3
    assert findings[1].swc == "107" and findings[1].cwe == "841"
    assert "checks-effects-interactions" in findings[1].remediation
    assert Finding.from_dict(__import__("dataclasses").asdict(findings[0])) == findings[0]
    assert findings[0].severity == Severity.MEDIUM


@pytest.mark.parametrize(
    "change",
    [
        {"impact": None},
        {"confidence": "unknown"},
        {"check": ""},
        {"elements": None},
        {"elements": []},
        {"elements": [None]},
        {"elements": [{"source_mapping": None}]},
    ],
)
def test_parser_rejects_invalid_detector(change):
    data = fixture()
    data["results"]["detectors"][0].update(change)
    with pytest.raises(ReportError):
        parse_report(data, {"A.sol": Source("A.sol", "contract A {}")})


@pytest.mark.parametrize(
    "impact,severity", [("Informational", Severity.INFO), ("Optimization", Severity.GAS)]
)
def test_parser_informational_levels(impact, severity):
    data = fixture()
    data["results"]["detectors"] = [
        dict(data["results"]["detectors"][0], impact=impact, check="new-detector")
    ]
    assert (
        parse_report(data, {"A.sol": Source("A.sol", "\n\ncontract A {}")})[0].severity == severity
    )
