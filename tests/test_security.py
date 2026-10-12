"""Hostile upload, CSRF, rate limit, retention, and deployment-policy regressions."""

import io
import re
import stat
import threading
import uuid
import zipfile

import pytest

from contract_radar import create_app
from contract_radar.config import ScannerConfig
from contract_radar.scanner.compiler import resolve_units
from contract_radar.scanner.source import load_sources
from contract_radar.services.jobs import JobService
from contract_radar.services.storage import ResultStore
from contract_radar.services.uploads import UploadError, UploadPolicy, prepare_path, prepare_upload

SOURCE = b"pragma solidity ^0.8.0; contract A {}"


def archive(entries, compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as bundle:
        for name, data in entries:
            if isinstance(name, str):
                raw_name = name
                name = zipfile.ZipInfo(name)
                name.filename = raw_name
                name.orig_filename = raw_name
                name.compress_type = compression
            bundle.writestr(name, data)
    stream.seek(0)
    return stream


@pytest.mark.parametrize(
    "filename", ["../A.sol", "/A.sol", "C:\\A.sol", "folder/A.sol", "A.exe", "A.txt"]
)
def test_bad_upload_names(tmp_path, filename):
    with pytest.raises(UploadError):
        prepare_upload(io.BytesIO(SOURCE), filename, tmp_path, UploadPolicy())
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x00" + SOURCE,
        b"\xff\xfe",
        b"MZpretendbinary",
        b"// contract A {}",
        b"hello coffee tax",
    ],
)
def test_content_validation_and_cleanup(tmp_path, data):
    with pytest.raises(UploadError):
        prepare_upload(io.BytesIO(data), "A.sol", tmp_path, UploadPolicy())
    assert not list(tmp_path.iterdir())


def test_request_and_direct_upload_size(client, tmp_path):
    assert (
        client.post(
            "/api/v1/scan", data={"contract": (io.BytesIO(b"x" * (2 * 1024 * 1024)), "A.sol")}
        ).status_code
        == 413
    )
    with pytest.raises(UploadError):
        prepare_upload(io.BytesIO(SOURCE), "A.sol", tmp_path, UploadPolicy(max_upload=10))


@pytest.mark.parametrize(
    "path",
    [
        "../evil.sol",
        "/evil.sol",
        "C:/evil.sol",
        "a/../../evil.sol",
        "a\\evil.sol",
        "//server/evil.sol",
        "CON.sol",
        "folder./A.sol",
        "a//A.sol",
        "./A.sol",
    ],
)
def test_zip_slip_and_windows_paths(tmp_path, path):
    with pytest.raises(UploadError):
        prepare_upload(archive([(path, SOURCE)]), "project.zip", tmp_path, UploadPolicy())
    assert not list(tmp_path.iterdir())


def test_zip_file_limits_duplicates_binary_and_scripts(tmp_path):
    for entries, policy in [
        ([("A.sol", SOURCE), ("a.sol", SOURCE)], UploadPolicy()),
        ([("A.sol", SOURCE), ("B.sol", SOURCE)], UploadPolicy(max_files=1)),
        ([("A.sol", SOURCE), ("B.sol", SOURCE)], UploadPolicy(max_extracted=40)),
        ([("A.sol", SOURCE), ("hardhat.config.js", b"process.exit()")], UploadPolicy()),
        ([("A.sol", b"\x00")], UploadPolicy()),
        ([], UploadPolicy()),
    ]:
        with pytest.raises(UploadError):
            prepare_upload(archive(entries), "project.zip", tmp_path, policy)
        assert not list(tmp_path.iterdir())


def test_zip_symlink_and_ratio(tmp_path):
    link = zipfile.ZipInfo("A.sol")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(UploadError):
        prepare_upload(archive([(link, SOURCE)]), "project.zip", tmp_path, UploadPolicy())
    with pytest.raises(UploadError):
        prepare_upload(
            archive([("A.sol", SOURCE + b" " * 100000)], zipfile.ZIP_DEFLATED),
            "project.zip",
            tmp_path,
            UploadPolicy(),
        )
    with pytest.raises(UploadError):
        prepare_upload(io.BytesIO(b"not a zip"), "project.zip", tmp_path, UploadPolicy())


def test_zip_multifile_imports_and_identical_names_isolated(tmp_path):
    entries = [
        ("src/A.sol", b'pragma solidity ^0.8.0; import "./B.sol"; contract A is B {}'),
        ("src/B.sol", b"pragma solidity <0.8.21 >=0.8.10; contract B {}"),
    ]
    first = prepare_upload(archive(entries), "project.zip", tmp_path, UploadPolicy())
    second = prepare_upload(archive(entries), "project.zip", tmp_path, UploadPolicy())
    assert first != second and first.parent == second.parent
    assert resolve_units(load_sources(first))[0].compiler == "0.8.20"
    assert (first / "src/B.sol").is_file()


def test_cli_directory_limits_and_cleanup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "A.sol").write_bytes(SOURCE)
    temp = tmp_path / "temp"
    with pytest.raises(UploadError):
        prepare_path(project, temp, UploadPolicy(max_upload=10))
    assert not list(temp.iterdir())


def test_csrf_and_security_headers(tmp_path):
    from conftest import fake_scan

    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": tmp_path,
            "SCAN_FUNCTION": fake_scan,
            "RATELIMIT_ENABLED": False,
        }
    )
    try:
        client = app.test_client()
        page = client.get("/")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)[1].decode()
        assert client.post("/", data={"contract": (io.BytesIO(SOURCE), "A.sol")}).status_code == 400
        assert (
            client.post(
                "/", data={"csrf_token": token, "contract": (io.BytesIO(SOURCE), "A.sol")}
            ).status_code
            == 303
        )
        response = client.post("/api/v1/scan", data={"contract": (io.BytesIO(SOURCE), "A.sol")})
        assert response.status_code == 202
        assert "'unsafe-inline'" not in response.headers["Content-Security-Policy"]
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "same-origin"
        assert (
            client.post(
                "/api/v1/scan",
                headers={"Origin": "https://evil.invalid"},
                data={"contract": (io.BytesIO(SOURCE), "A.sol")},
            ).status_code
            == 403
        )
    finally:
        app.extensions["contract_radar_jobs"].shutdown()


def test_https_csrf_upload_requires_token_and_same_origin_referrer(tmp_path):
    from conftest import fake_scan

    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": tmp_path,
            "SCAN_FUNCTION": fake_scan,
            "RATELIMIT_ENABLED": False,
            "SESSION_COOKIE_SECURE": True,
        }
    )
    try:
        client = app.test_client()
        base = "https://radar.example"
        page = client.get("/", base_url=base)
        assert page.headers["Referrer-Policy"] == "same-origin"
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)[1].decode()
        for referrer in [None, "https://foreign.example/"]:
            response = client.post(
                "/",
                base_url=base,
                headers={"Referer": referrer} if referrer else {},
                data={"csrf_token": token, "contract": (io.BytesIO(SOURCE), "A.sol")},
            )
            assert response.status_code == 400
        assert (
            client.post(
                "/",
                base_url=base,
                headers={"Referer": base + "/"},
                data={"contract": (io.BytesIO(SOURCE), "A.sol")},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/",
                base_url=base,
                headers={"Referer": base + "/"},
                data={"csrf_token": token, "contract": (io.BytesIO(SOURCE), "A.sol")},
            ).status_code
            == 303
        )
    finally:
        app.extensions["contract_radar_jobs"].shutdown()


def test_scan_rate_limit(tmp_path):
    from conftest import fake_scan

    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": tmp_path,
            "SCAN_FUNCTION": fake_scan,
            "SCAN_RATE_LIMIT": "1 per minute",
            "WTF_CSRF_ENABLED": False,
        }
    )
    try:
        client = app.test_client()
        assert (
            client.post(
                "/api/v1/scan", data={"contract": (io.BytesIO(SOURCE), "A.sol")}
            ).status_code
            == 202
        )
        assert (
            client.post(
                "/api/v1/scan", data={"contract": (io.BytesIO(SOURCE), "A.sol")}
            ).status_code
            == 429
        )
    finally:
        app.extensions["contract_radar_jobs"].shutdown()


def test_production_requires_secret_and_disables_debug(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTRACT_RADAR_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app({"DATA_DIR": tmp_path})
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("CONTRACT_RADAR_DEBUG", "true")
    app = create_app({"DATA_DIR": tmp_path})
    try:
        assert not app.debug
    finally:
        app.extensions["contract_radar_jobs"].shutdown()


def test_single_process_lock_and_abandoned_temp_cleanup(tmp_path):
    abandoned = tmp_path / "temp" / str(uuid.uuid4())
    abandoned.mkdir(parents=True)
    (abandoned / "A.sol").write_bytes(SOURCE)
    store = ResultStore(tmp_path / "db")
    jobs = JobService(store, ScannerConfig())
    try:
        assert not abandoned.exists()
        # Use a different thread because filelock intentionally permits same-thread reentry.
        failures = []

        def duplicate():
            try:
                other = JobService(store, ScannerConfig())
                other.shutdown()
            except RuntimeError as exc:
                failures.append(str(exc))

        thread = threading.Thread(target=duplicate)
        thread.start()
        thread.join()
        assert failures
    finally:
        jobs.shutdown()
