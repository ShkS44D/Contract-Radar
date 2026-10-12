"""HTTP state flow, escaped reports, exports, CLI, and bounded job behavior."""

import io
import json
import threading
import time
import uuid
from unittest.mock import patch

import pytest

from sentinel.cli import main
from sentinel.config import ScannerConfig
from sentinel.scanner.models import ScanResult, ScanState
from sentinel.services.exports import to_json, to_markdown, to_pdf, to_sarif
from sentinel.services.jobs import JobService, QueueFull
from sentinel.services.storage import ResultStore


def upload(
    client, url="/api/v1/scan", filename="A.sol", data=b"pragma solidity ^0.8.0; contract A {}"
):
    return client.post(url, data={"contract": (io.BytesIO(data), filename)})


def wait_result(app, scan_id):
    for _ in range(100):
        result = app.extensions["sentinel_store"].get(scan_id)
        if result.state not in {ScanState.QUEUED, ScanState.RUNNING}:
            return result
        time.sleep(0.01)
    pytest.fail("Fake background scan did not finish")


def test_upload_report_exports_and_source_cleanup(client, app):
    response = upload(client)
    assert response.status_code == 202
    scan_id = response.json["scan_id"]
    UUID = uuid.UUID(scan_id)
    assert UUID.version == 4
    result = wait_result(app, scan_id)
    assert result.score is not None
    assert client.get(response.headers["Location"]).json["state"] == "completed"
    report = client.get(f"/report/{scan_id}")
    assert report.status_code == 200
    assert b"&lt;script&gt;" in report.data and b'<script>alert("x")</script>' not in report.data
    for format in ["json", "sarif", "md", "pdf"]:
        exported = client.get(f"/report/{scan_id}/export/{format}")
        assert exported.status_code == 200
        assert exported.headers["Content-Disposition"].startswith("attachment")
    app.extensions["sentinel_jobs"].shutdown()
    assert not list((app.config["DATA_DIR"] / "temp").iterdir())


def test_original_web_flow(client, app):
    assert client.get("/").status_code == 200
    response = upload(client, "/")
    assert response.status_code == 303
    scan_id = response.headers["Location"].split("/")[-1]
    wait_result(app, scan_id)
    assert b"Scan report" in client.get(response.headers["Location"]).data


def test_failed_report_has_no_score(client, app):
    scan_id = str(uuid.uuid4())
    app.extensions["sentinel_store"].save(
        ScanResult(scan_id, ScanState.COMPILE_ERROR, "A.sol", diagnostics="<compiler error>")
    )
    page = client.get(f"/report/{scan_id}").data
    assert b"No score is available" in page and b"gauge" not in page
    data = client.get(f"/api/v1/scan/{scan_id}").json
    assert data["score"] is None and data["grade"] is None


def test_loading_and_early_export(client, app):
    scan_id = str(uuid.uuid4())
    app.extensions["sentinel_store"].save(ScanResult(scan_id, ScanState.RUNNING, "A.sol"))
    assert b"Analyzing your contract" in client.get(f"/report/{scan_id}").data
    assert client.get(f"/report/{scan_id}/export/json").status_code == 409


def test_validation_and_lookup_errors(client):
    assert client.post("/api/v1/scan").status_code == 400
    assert upload(client, filename="a.exe").status_code == 400
    assert upload(client, data=b"\x00binary").status_code == 400
    assert client.get("/report/not-a-uuid").status_code == 404
    assert client.get(f"/api/v1/scan/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/openapi.json").json["openapi"] == "3.0.3"
    assert client.get("/health").json["status"] == "ok"


def test_export_encodings_and_failure_invocation():
    result = ScanResult("id", ScanState.TIMEOUT, "<bad>.sol", diagnostics="timeout")
    assert json.loads(to_json(result))["score"] is None
    assert not json.loads(to_sarif(result))["runs"][0]["invocations"][0]["executionSuccessful"]
    assert b"Unscored" in to_markdown(result)
    assert to_pdf(result).startswith(b"%PDF")


def test_cli_exit_codes(tmp_path, capsys):
    file = tmp_path / "A.sol"
    file.write_text("contract A {}")
    from conftest import fake_scan

    with patch("sentinel.cli.scan_project", side_effect=fake_scan):
        assert main(["scan", str(file), "--fail-on", "high"]) == 1
        assert json.loads(capsys.readouterr().out)["state"] == "completed"
        output = tmp_path / "report.md"
        assert main(["scan", str(file), "--format", "md", "-o", str(output)]) == 0
        assert output.read_text().startswith("# Solidity Sentinel")
    with patch(
        "sentinel.cli.scan_project", return_value=ScanResult("id", ScanState.COMPILE_ERROR, "A.sol")
    ):
        assert main(["scan", str(file)]) == 2
    assert main(["scan", str(tmp_path / "missing.sol")]) == 2


def test_queue_bound_and_restart_recovery(tmp_path):
    event = threading.Event()

    def blocked(root, scan_id, filename, config):
        event.wait(5)
        return ScanResult(scan_id, ScanState.TIMEOUT, filename)

    store = ResultStore(tmp_path / "db")
    jobs = JobService(store, ScannerConfig(), workers=1, queue_size=0, scan=blocked)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    result = jobs.submit(first, "A.sol")
    try:
        with pytest.raises(QueueFull):
            jobs.submit(second, "A.sol")
        assert not second.exists()
    finally:
        event.set()
        jobs.shutdown()
    assert not first.exists()
    assert store.get(result.scan_id).score is None
    pending = ScanResult(str(uuid.uuid4()), ScanState.RUNNING, "B.sol")
    store.save(pending)
    store.recover()
    assert store.get(pending.scan_id).state == ScanState.ENGINE_ERROR


def test_expired_reports_removed(tmp_path):
    store = ResultStore(tmp_path / "db", retention_hours=0.000001)
    result = ScanResult(str(uuid.uuid4()), ScanState.COMPILE_ERROR, "A.sol")
    store.save(result)
    time.sleep(0.01)
    assert store.get(result.scan_id) is None


def test_uploaded_crlf_preserves_source_lines(tmp_path):
    from sentinel.scanner.source import load_sources
    from sentinel.services.uploads import UploadPolicy, prepare_upload

    root = prepare_upload(
        io.BytesIO(b"pragma solidity ^0.8.0;\r\ncontract A {}\r\n"),
        "A.sol",
        tmp_path,
        UploadPolicy(),
    )
    source = next(iter(load_sources(root).values()))
    assert source.text.splitlines() == ["pragma solidity ^0.8.0;", "contract A {}"]
