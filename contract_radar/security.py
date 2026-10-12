"""Browser protections, deliberate API CSRF policy, and bounded admission rate."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import Flask, Response, abort, request
from flask.typing import ResponseReturnValue
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect


def configure_security(app: Flask) -> None:
    """Install CSRF, same-origin API checks, security headers, and scan limits."""
    csrf = CSRFProtect(app)
    csrf.exempt(app.blueprints["api"])
    limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])
    app.extensions["contract_radar_limiter"] = limiter

    def local_view(
        original: Callable[..., ResponseReturnValue],
    ) -> Callable[..., ResponseReturnValue]:
        @wraps(original, updated=())
        def invoke(*args: Any, **kwargs: Any) -> ResponseReturnValue:
            return original(*args, **kwargs)

        return invoke

    for endpoint in ["web.index", "api.create_scan"]:
        app.view_functions[endpoint] = cast(
            Callable[..., ResponseReturnValue],
            limiter.shared_limit(
                app.config["SCAN_RATE_LIMIT"], scope="scan-admission", methods=["POST"]
            )(local_view(cast(Callable[..., ResponseReturnValue], app.view_functions[endpoint]))),
        )

    @app.before_request
    def api_origin() -> None:
        # API has no cookie authentication. Reject foreign browser origins; CLI clients omit Origin.
        if request.path == "/api/v1/scan" and request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                abort(403, description="Cross-origin browser API uploads are not allowed")
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                abort(403, description="Cross-site browser API uploads are not allowed")

        if (
            app.config["EXECUTION_MODE"] == "request"
            and request.method == "POST"
            and request.path in {"/", "/api/v1/scan"}
        ):
            store = app.extensions["contract_radar_store"]
            if not store.admit_client(get_remote_address()):
                abort(429, description="Hosted scans are limited to 10 submissions per minute")

    @app.after_request
    def headers(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # HTTPS CSRF validation needs same-origin Referer headers. Report URLs
        # still never leak through Referer on links to external sites.
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
