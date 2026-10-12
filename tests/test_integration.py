"""Real pinned-engine samples; opt in with SENTINEL_RUN_INTEGRATION=1."""

import io
import json
import os
from pathlib import Path

import pytest

from sentinel.config import ScannerConfig
from sentinel.scanner.engine import scan_project
from sentinel.scanner.models import ScanState, Severity
from sentinel.services.uploads import UploadPolicy, prepare_upload

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "samples/expected.json").read_text())
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("SENTINEL_RUN_INTEGRATION") != "1",
        reason="Set SENTINEL_RUN_INTEGRATION=1 to run real compiler scans",
    ),
]


@pytest.mark.parametrize("filename", list(EXPECTED["samples"]))
def test_real_samples(filename, tmp_path):
    root = prepare_upload(
        io.BytesIO((ROOT / "samples" / filename).read_bytes()), filename, tmp_path, UploadPolicy()
    )
    result = scan_project(root, "integration", filename, ScannerConfig(timeout=120))
    assert result.state == ScanState.COMPLETED, result.diagnostics
    assert result.metadata["slither_version"] == "0.11.6"
    rules = {f.rule_id for f in result.findings}
    expected = EXPECTED["samples"][filename]
    assert set(expected["required"]) <= rules, (filename, rules)
    assert not set(expected["forbidden"]) & rules, (filename, rules)
    if expected.get("no_material_findings"):
        assert not any(f.severity.rank <= Severity.MEDIUM.rank for f in result.findings)


def test_real_broken_source(tmp_path):
    root = prepare_upload(
        io.BytesIO(b"pragma solidity 0.8.30; contract Broken { function x( }"),
        "Broken.sol",
        tmp_path,
        UploadPolicy(),
    )
    result = scan_project(root, "integration", "Broken.sol")
    assert result.state == ScanState.COMPILE_ERROR
    assert result.score is None and not result.findings


def test_real_comments_strings_and_identifier_regression(tmp_path):
    text = b"""pragma solidity 0.8.30;
// function mint() external {} selfdestruct blacklist pausable tx.origin
contract Coffee {
    string public constant LABEL = "selfdestruct blacklist tax pausable delegatecall";
    uint256 public coffee;
    uint256 public feed;
    function update(uint256 value) external { coffee = value; feed = value; }
}"""
    root = prepare_upload(io.BytesIO(text), "Coffee.sol", tmp_path, UploadPolicy())
    result = scan_project(root, "integration", "Coffee.sol")
    assert result.state == ScanState.COMPLETED, result.diagnostics
    assert not any(f.rule_id.startswith("SS-") for f in result.findings)
