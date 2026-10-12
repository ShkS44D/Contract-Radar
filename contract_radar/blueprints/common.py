"""Shared upload and report lookup helpers."""

from pathlib import Path
from uuid import UUID

from flask import abort, current_app, request
from werkzeug.utils import secure_filename

from contract_radar.scanner.models import ScanResult
from contract_radar.services.jobs import JobService, QueueFull
from contract_radar.services.storage import ResultStore
from contract_radar.services.uploads import UploadError, prepare_upload


def submit_upload() -> ScanResult:
    """Validate multipart input, prepare isolated sources, and enqueue a scan."""
    upload = request.files.get("contract") or request.files.get("file")
    if upload is None or not upload.filename:
        abort(400, description="Select a Solidity file or project archive")
    try:
        root = prepare_upload(
            upload.stream,
            upload.filename,
            Path(current_app.config["DATA_DIR"]) / "temp",
            current_app.extensions["contract_radar_upload_policy"],
        )
        label = (secure_filename(upload.filename) or "contract.sol")[:150]
        jobs: JobService = current_app.extensions["contract_radar_jobs"]
        return jobs.submit(root, label)
    except UploadError as exc:
        abort(400, description=str(exc))
    except QueueFull as exc:
        abort(503, description=str(exc))


def get_result(scan_id: str) -> ScanResult:
    """Require a canonical unguessable UUID and a retained report."""
    try:
        if str(UUID(scan_id)) != scan_id:
            raise ValueError
    except ValueError:
        abort(404, description="Report not found or expired")
    store: ResultStore = current_app.extensions["contract_radar_store"]
    result = store.get(scan_id)
    if result is None:
        abort(404, description="Report not found or expired")
    return result
