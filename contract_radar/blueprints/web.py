"""Browser upload, job progress, reports, and downloadable exports."""

from flask import Blueprint, Response, abort, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from contract_radar.scanner.models import ScanState, Severity
from contract_radar.services.exports import EXPORTERS

from .common import get_result, submit_upload

web = Blueprint("web", __name__)


@web.get("/favicon.ico")
def favicon() -> ResponseReturnValue:
    """Serve the brand icon at the conventional browser favicon URL."""
    return redirect(url_for("static", filename="images/favicon.svg", v="radar-2"))


@web.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    """Preserve upload -> report flow while scans run in the background."""
    from flask import request

    if request.method == "POST":
        result = submit_upload()
        return redirect(url_for("web.report", scan_id=result.scan_id), code=303)
    return render_template("index.html")


@web.get("/report/<scan_id>")
def report(scan_id: str) -> ResponseReturnValue:
    """Render loading, failed, or completed results without scoring failures."""
    result = get_result(scan_id)
    if result.state in {ScanState.QUEUED, ScanState.RUNNING}:
        return render_template("loading.html", result=result)
    if result.state != ScanState.COMPLETED:
        return render_template(
            "error.html",
            title="Scan did not complete",
            message="No score is available because analysis failed.",
            result=result,
        )
    summary = {
        severity.value: sum(f.severity == severity for f in result.findings)
        for severity in Severity
    }
    return render_template("report.html", result=result, summary=summary)


@web.get("/report/<scan_id>/export/<format>")
def export(scan_id: str, format: str) -> ResponseReturnValue:
    """Download one normalized export for a terminal result."""
    result = get_result(scan_id)
    if format not in EXPORTERS:
        abort(404)
    if result.state in {ScanState.QUEUED, ScanState.RUNNING}:
        abort(409, description="The scan is still running")
    exporter, mimetype = EXPORTERS[format]
    extension = "sarif" if format == "sarif" else format
    return Response(
        exporter(result),
        content_type=mimetype,
        headers={
            "Content-Disposition": f'attachment; filename="contract-radar-{scan_id}.{extension}"'
        },
    )
