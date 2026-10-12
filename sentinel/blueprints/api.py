"""Versioned multipart scan API and machine-readable OpenAPI contract."""

from flask import Blueprint, jsonify, url_for
from flask.typing import ResponseReturnValue

from .common import get_result, submit_upload

api = Blueprint("api", __name__, url_prefix="/api/v1")


@api.post("/scan")
def create_scan() -> ResponseReturnValue:
    """Accept a scan asynchronously and return its status URL."""
    result = submit_upload()
    status_url = url_for("api.read_scan", scan_id=result.scan_id)
    return (
        jsonify(
            **result.to_dict(),
            status_url=status_url,
            report_url=url_for("web.report", scan_id=result.scan_id),
        ),
        202,
        {"Location": status_url, "Retry-After": "2"},
    )


@api.get("/scan/<scan_id>")
def read_scan(scan_id: str) -> ResponseReturnValue:
    """Read current state or terminal results; use state rather than a guessed percentage."""
    return jsonify(get_result(scan_id).to_dict())


@api.get("/openapi.json")
def openapi() -> ResponseReturnValue:
    """Expose the OpenAPI 3.0.3 upload and result schema."""
    from sentinel.openapi import SPEC

    return jsonify(SPEC)
