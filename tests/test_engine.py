"""Engine failures must never become clean scored results."""

import json
import os
import sys
from unittest.mock import patch

import pytest

from contract_radar.config import ScannerConfig
from contract_radar.scanner.compiler import CompileError, pragma_specs, resolve_units
from contract_radar.scanner.engine import scan_project, scanner_environment
from contract_radar.scanner.models import ScanResult, ScanState
from contract_radar.scanner.parser import ReportError, validate_report
from contract_radar.scanner.process import (
    OutputLimitError,
    ProcessResult,
    ProcessTimeout,
    run_process,
)
from contract_radar.scanner.source import Source, mask_source


def test_mask_preserves_lines_and_escaped_strings():
    original = 'contract A { string s = "a\\"//mint"; /* multi\nline */ uint coffee; } // mint'
    masked = mask_source(original)
    assert len(masked) == len(original)
    assert masked.count("\n") == original.count("\n")
    assert "mint" not in masked
    assert "coffee" in masked
    assert Source("A.sol", original).sloc == 2


@pytest.mark.parametrize(
    "pragma,version",
    [
        ("^0.8.0", "0.8.30"),
        (">=0.7.0 <0.8.0", "0.7.6"),
        ("0.8.20", "0.8.20"),
        ("^0.6.0 || ^0.8.0", "0.8.30"),
        (">= 0.8.10 < 0.8.21", "0.8.20"),
    ],
)
def test_pragma_ranges(pragma, version):
    units = resolve_units({"A.sol": Source("A.sol", f"pragma solidity {pragma}; contract A {{}}")})
    assert units[0].compiler == version


def test_multiple_pragmas_and_independent_roots():
    sources = {
        "A.sol": Source("A.sol", 'pragma solidity ^0.8.0; import "./B.sol";'),
        "B.sol": Source("B.sol", "pragma solidity <0.8.21 >=0.8.10;"),
        "C.sol": Source("C.sol", "pragma solidity ^0.7.0;"),
    }
    assert [u.compiler for u in resolve_units(sources)] == ["0.8.20", "0.7.6"]
    sources["B.sol"] = Source("B.sol", "pragma solidity ^0.6.0;")
    with pytest.raises(CompileError):
        resolve_units(sources)


@pytest.mark.parametrize(
    "text",
    [
        'import "../missing.sol";',
        'import "C:/outside.sol";',
        "pragma solidity nonsense;",
        "pragma solidity >=9.0.0;",
    ],
)
def test_compiler_rejects_bad_inputs(text):
    with pytest.raises(CompileError):
        resolve_units({"A.sol": Source("A.sol", text)})


def test_missing_pragma_and_comments():
    source = Source("A.sol", "// pragma solidity ^0.4.0;\ncontract A {}")
    assert not pragma_specs(source)
    unit = resolve_units({"A.sol": source})[0]
    assert unit.compiler == "0.8.30"
    assert unit.warnings
    with pytest.raises(CompileError):
        resolve_units({})


@pytest.mark.parametrize(
    "data", [{}, {"success": True}, {"success": True, "results": {"detectors": [None]}}]
)
def test_bad_report_never_clean(data):
    with pytest.raises(ReportError):
        validate_report(data)


def test_compile_report_failure():
    with pytest.raises(CompileError):
        validate_report({"success": False, "error": "bad Solidity"})


@pytest.mark.parametrize(
    "error,state",
    [
        (ProcessTimeout("deadline"), ScanState.TIMEOUT),
        (CompileError("compile"), ScanState.COMPILE_ERROR),
        (FileNotFoundError("slither"), ScanState.ENGINE_ERROR),
    ],
)
def test_engine_failure_states(tmp_path, error, state):
    (tmp_path / "A.sol").write_text("pragma solidity ^0.8.0; contract A {}")
    with patch("contract_radar.scanner.engine.ensure_compiler", side_effect=error):
        result = scan_project(tmp_path, "id", "A.sol")
    assert result.state == state
    assert result.score is None and result.grade is None
    assert not result.findings


def test_engine_missing_output(tmp_path):
    (tmp_path / "A.sol").write_text("contract A {}")
    with (
        patch("contract_radar.scanner.engine.ensure_compiler"),
        patch(
            "contract_radar.scanner.engine.run_process", return_value=ProcessResult(1, "", "failed")
        ),
    ):
        result = scan_project(tmp_path, "id", "A.sol")
    assert result.state == ScanState.ENGINE_ERROR
    assert "failed" in result.diagnostics


def test_engine_success(tmp_path):
    (tmp_path / "A.sol").write_text("contract A {}")

    def run(args, **kwargs):
        from pathlib import Path

        Path(args[-1]).write_text(
            json.dumps(
                {
                    "success": True,
                    "results": {"detectors": []},
                    "contract_radar_metadata": {"slither_version": "test"},
                    "contract_radar_facts": {"functions": [], "contracts": ["A.sol:A"]},
                }
            )
        )
        return ProcessResult(0, "", "")

    with (
        patch("contract_radar.scanner.engine.ensure_compiler"),
        patch("contract_radar.scanner.engine.run_process", side_effect=run),
    ):
        result = scan_project(tmp_path, "id", "A.sol")
    assert result.state == ScanState.COMPLETED
    assert ScanResult.from_dict(result.to_dict()) == result


def test_no_analyzed_declarations_is_not_clean(tmp_path):
    (tmp_path / "A.sol").write_text("pragma solidity ^0.8.0;")

    def run(args, **kwargs):
        from pathlib import Path

        Path(args[-1]).write_text(
            json.dumps(
                {
                    "success": True,
                    "results": {"detectors": []},
                    "contract_radar_metadata": {"slither_version": "test"},
                    "contract_radar_facts": {"functions": [], "contracts": []},
                }
            )
        )
        return ProcessResult(0, "", "")

    with (
        patch("contract_radar.scanner.engine.ensure_compiler"),
        patch("contract_radar.scanner.engine.run_process", side_effect=run),
    ):
        result = scan_project(tmp_path, "id", "A.sol")
    assert result.state == ScanState.COMPILE_ERROR and result.score is None


def test_failure_invariant():
    with pytest.raises(ValueError):
        ScanResult("id", ScanState.COMPILE_ERROR, "A.sol", score=100)


def test_child_environment_hides_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "hidden")
    monkeypatch.setenv("OPENAI_API_KEY", "hidden")
    env = scanner_environment(ScannerConfig())
    assert "SECRET_KEY" not in env and "OPENAI_API_KEY" not in env


def test_real_subprocess_deadline_and_output_limit(tmp_path):
    with pytest.raises(ProcessTimeout):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            cwd=tmp_path,
            env=dict(os.environ),
            timeout=0.15,
        )
    with pytest.raises(OutputLimitError):
        run_process(
            [sys.executable, "-c", "print('x'*10000)"],
            cwd=tmp_path,
            env=dict(os.environ),
            timeout=5,
            output_limit=100,
        )
    result = run_process(
        [sys.executable, "-c", "print('ok')"], cwd=tmp_path, env=dict(os.environ), timeout=5
    )
    assert result.returncode == 0 and result.stdout.strip() == "ok"


def test_bundled_offline_compiler_needs_no_writes(tmp_path):
    from contract_radar.scanner.compiler import ensure_compiler

    cache = tmp_path / ".solc-select"
    artifact = cache / "artifacts/solc-0.8.30/solc-0.8.30"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"test-binary")
    with patch(
        "contract_radar.scanner.compiler.FileLock", side_effect=AssertionError("Read-only bundle")
    ):
        ensure_compiler("0.8.30", cache=cache, env={}, timeout=1, offline=True)
    assert not (cache / "install.lock").exists()


def test_missing_offline_compiler_has_no_side_effects(tmp_path):
    from contract_radar.scanner.compiler import ensure_compiler

    cache = tmp_path / ".solc-select"
    with pytest.raises(CompileError, match="offline mode"):
        ensure_compiler("0.8.30", cache=cache, env={}, timeout=1, offline=True)
    assert not cache.exists()
