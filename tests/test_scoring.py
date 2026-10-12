"""Scoring properties, transparent breakdowns, and failure invariants."""

from dataclasses import replace

import pytest

from sentinel.scanner.models import Confidence, Finding, ScanResult, ScanState, Severity
from sentinel.scanner.scoring import apply_score


def finding(severity=Severity.HIGH, confidence=Confidence.HIGH, rule="rule", line=1):
    return Finding(rule, "Finding", severity, confidence, "why", "fix", "A.sol", line, line)


def score(findings):
    return apply_score(ScanResult("id", ScanState.COMPLETED, "A.sol", findings))


def test_empty_completed_score_is_observed_clean():
    result = score([])
    assert (result.score, result.grade, result.risk) == (100, "A", "Low")


def test_confidence_and_severity_monotonicity():
    assert score([finding(confidence=Confidence.LOW)]).score > score([finding()]).score
    assert score([finding(Severity.LOW)]).score > score([finding()]).score
    assert score([finding()]).risk == "High"
    assert score([finding(Severity.CRITICAL)]).risk == "Critical"


def test_diminishing_returns_cap_and_duplicate_removal():
    result = score([finding(line=i) for i in range(1, 101)])
    assert result.score == 67
    assert result.breakdown[0]["penalty"] == 33
    assert score([finding(), finding()]).score == score([finding()]).score
    assert (
        score([finding(line=2), finding(line=1)]).score
        == score([finding(line=1), finding(line=2)]).score
    )


def test_many_distinct_rules_are_capped():
    result = score([finding(rule=str(i)) for i in range(20)])
    assert result.score == 0 and result.grade == "F"
    assert score([finding(Severity.INFO), finding(Severity.GAS, rule="gas")]).score == 100


@pytest.mark.parametrize("state", [state for state in ScanState if state != ScanState.COMPLETED])
def test_failures_cannot_be_scored(state):
    with pytest.raises(ValueError):
        apply_score(ScanResult("id", state, "A.sol"))


def test_mixed_severity_group_and_serialization():
    result = score([finding(), finding(Severity.LOW, line=2)])
    assert result.breakdown[0]["cap"] == 33
    assert result.breakdown[0]["weighted_instances"] == [22, 4]
    assert ScanResult.from_dict(result.to_dict()) == result
    with pytest.raises(ValueError):
        replace(result, state=ScanState.ENGINE_ERROR)
