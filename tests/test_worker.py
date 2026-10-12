"""The process adapter is included in coverage and must retain failure envelopes."""

import json
from unittest.mock import patch

import pytest

from sentinel.scanner import worker
from sentinel.scanner.facts import AnalysisFacts


def test_worker_main_success(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["worker", "A.sol", str(output)])

    def cli(args, **kwargs):
        from subprocess import CompletedProcess

        output.write_text(json.dumps({"success": True, "results": {}}))
        return CompletedProcess(args, 0)

    with (
        patch.object(worker, "collect_facts", return_value=AnalysisFacts()),
        patch.object(worker.subprocess, "run", side_effect=cli),
    ):
        assert worker.main() == 0
    data = json.loads(output.read_text())
    assert data["sentinel_facts"] == {"functions": [], "contracts": []}
    assert data["results"]["detectors"] == []
    assert data["sentinel_metadata"]["slither_version"] == "0.11.6"


@pytest.mark.parametrize("kind", ["crytic", "slither"])
def test_worker_compile_failure(tmp_path, monkeypatch, kind):
    from crytic_compile.platform.exceptions import InvalidCompilation
    from slither.exceptions import SlitherError

    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["worker", "A.sol", str(output)])
    error = (
        InvalidCompilation("bad") if kind == "crytic" else SlitherError("Invalid compilation: bad")
    )
    with patch.object(worker, "collect_facts", side_effect=error):
        assert worker.main() == 2
    assert json.loads(output.read_text())["success"] is False


def test_worker_other_errors_are_not_compilation(tmp_path, monkeypatch):
    from slither.exceptions import SlitherError

    monkeypatch.setattr("sys.argv", ["worker", "A.sol", str(tmp_path / "out.json")])
    with (
        patch.object(
            worker, "collect_facts", side_effect=SlitherError("Unexpected engine problem")
        ),
        pytest.raises(SlitherError),
    ):
        worker.main()
