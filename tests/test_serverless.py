"""Serverless lifecycle, shared admission, persistence, and storage failures."""

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from contract_radar import create_app
from contract_radar.config import ScannerConfig
from contract_radar.scanner.models import ScanResult, ScanState
from contract_radar.services.jobs import QueueFull
from contract_radar.services.serverless import (
    RedisResultStore,
    RequestScanService,
    StorageUnavailable,
)


def store():
    return RedisResultStore("https://example.upstash.io", "test-token")


def test_redis_roundtrip_retention_and_missing():
    backend = store()
    result = ScanResult("id", ScanState.COMPILE_ERROR, "A.sol", diagnostics="bad source")
    with patch.object(backend, "command") as command:
        backend.save(result)
        args = command.call_args.args
        assert args[:2] == ("SET", "radar:report:id")
        assert args[-2] == "EX" and 0 < args[-1] <= 86400
        command.return_value = args[2]
        assert backend.get("id").state == ScanState.COMPILE_ERROR
        command.return_value = None
        assert backend.get("missing") is None
    result.metadata["submitted_at"] = 0
    with patch.object(backend, "command") as command:
        backend.save(result)
        command.assert_not_called()


@pytest.mark.parametrize("url,token", [("http://example.com", "x"), ("https://example.com", "")])
def test_storage_requires_secure_configuration(url, token):
    with pytest.raises(ValueError):
        RedisResultStore(url, token)


def test_rest_command_and_unavailable():
    backend = store()
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"result":"OK"}'
    with patch("contract_radar.services.serverless.urlopen", return_value=response) as opened:
        assert backend.command("PING") == "OK"
        request = opened.call_args.args[0]
        assert json.loads(request.data) == ["PING"]
        assert request.get_header("Authorization") == "Bearer test-token"
        assert opened.call_args.kwargs["timeout"] == 8
    with patch("contract_radar.services.serverless.urlopen", side_effect=URLError("down")):
        with pytest.raises(StorageUnavailable, match="temporarily unavailable"):
            backend.command("GET", "id")


@pytest.mark.parametrize(
    "payload",
    [b'{"error":"bad"}', b"{}", b"not-json", b"x" * 2000001],
    ids=["error", "missing", "invalid", "oversized"],
)
def test_invalid_storage_response_fails_closed(payload):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = payload
    with patch("contract_radar.services.serverless.urlopen", return_value=response):
        with pytest.raises(StorageUnavailable):
            store().command("GET", "id")


def test_atomic_limits_and_owned_lease():
    backend = store()
    with patch.object(backend, "command", return_value=10) as command:
        assert backend.admit_client("127.0.0.1")
        assert "127.0.0.1" not in str(command.call_args)
        command.return_value = 11
        assert not backend.admit_client("127.0.0.1")
        command.return_value = "OK"
        assert backend.acquire("owner")
        command.return_value = None
        assert not backend.acquire("owner")
        backend.release("owner")
        assert "ARGV[1]" in command.call_args.args[1]


@pytest.mark.parametrize("outcome", ["completed", "compile_error", "raise"])
def test_sources_removed_before_terminal_save(tmp_path, outcome):
    backend = MagicMock(spec=RedisResultStore)
    backend.acquire.return_value = True
    root = tmp_path / "source"
    root.mkdir()
    (root / "A.sol").write_text("contract A {}")

    def scan(root, scan_id, filename, config):
        if outcome == "raise":
            raise RuntimeError("engine down")
        return ScanResult(scan_id, ScanState(outcome), filename)

    backend.save.side_effect = lambda result: not root.exists() or pytest.fail("Source retained")
    result = RequestScanService(backend, ScannerConfig(), scan).submit(root, "A.sol")
    assert not root.exists()
    assert result.state == (ScanState.ENGINE_ERROR if outcome == "raise" else ScanState(outcome))
    if result.state != ScanState.COMPLETED:
        assert result.score is None
    backend.release.assert_called_once_with(result.scan_id)
    backend.save.assert_called_once()


def test_busy_and_storage_failure_delete_upload(tmp_path):
    for error in [False, StorageUnavailable("down")]:
        root = tmp_path / "source"
        root.mkdir()
        backend = MagicMock(spec=RedisResultStore)
        if error:
            backend.acquire.side_effect = error
        else:
            backend.acquire.return_value = False
        with pytest.raises(StorageUnavailable if error else QueueFull):
            RequestScanService(backend, ScannerConfig()).submit(root, "A.sol")
        assert not root.exists()
        backend.save.assert_not_called()


def test_cleanup_failure_cannot_publish_score(tmp_path):
    backend = MagicMock(spec=RedisResultStore)
    backend.acquire.return_value = True

    def scan(root, scan_id, filename, config):
        return ScanResult(scan_id, ScanState.COMPLETED, filename, score=100)

    with patch("contract_radar.services.serverless.shutil.rmtree", side_effect=OSError("blocked")):
        result = RequestScanService(backend, ScannerConfig(), scan).submit(tmp_path, "A.sol")
    assert result.state == ScanState.ENGINE_ERROR and result.score is None


def test_request_mode_http_and_fail_closed(tmp_path):
    backend = MagicMock(spec=RedisResultStore)
    backend.admit_client.return_value = True
    backend.acquire.return_value = True

    def scan(root, scan_id, filename, config):
        return ScanResult(scan_id, ScanState.COMPILE_ERROR, filename)

    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": tmp_path,
            "EXECUTION_MODE": "request",
            "RESULT_STORE": backend,
            "SCAN_FUNCTION": scan,
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
        }
    )
    client = app.test_client()
    response = client.post(
        "/api/v1/scan", data={"contract": (io.BytesIO(b"contract A {}"), "A.sol")}
    )
    assert response.status_code == 200
    assert response.json["state"] == "compile_error" and response.json["score"] is None
    assert not list((tmp_path / "temp").iterdir())
    backend.get.side_effect = StorageUnavailable("Report storage unavailable")
    assert client.get(response.json["status_url"]).status_code == 503
    backend.admit_client.return_value = False
    assert client.post("/api/v1/scan").status_code == 429
