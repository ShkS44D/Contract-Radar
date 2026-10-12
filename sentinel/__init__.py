"""Solidity Sentinel application package."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flask import Flask

__version__ = "2.0.0"


def create_app(config: dict[str, Any] | None = None) -> "Flask":
    """Create the Flask application with explicit development/production settings."""
    import logging
    import os
    import secrets
    from pathlib import Path

    from dotenv import load_dotenv
    from flask import Flask, jsonify, request
    from flask.typing import ResponseReturnValue
    from werkzeug.exceptions import HTTPException

    from sentinel.config import ScannerConfig
    from sentinel.services.jobs import JobService
    from sentinel.services.storage import ResultStore
    from sentinel.services.uploads import UploadPolicy

    load_dotenv()
    app = Flask(__name__)
    production = os.getenv("SENTINEL_ENV", "development") == "production"
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or (None if production else secrets.token_hex(32)),
        DEBUG=os.getenv("SENTINEL_DEBUG", "false").lower() == "true" and not production,
        DATA_DIR=Path(os.getenv("SENTINEL_DATA_DIR", ".sentinel")).resolve(),
        MAX_CONTENT_LENGTH=int(os.getenv("SENTINEL_MAX_UPLOAD_MB", "2")) * 1024 * 1024,
        MAX_EXTRACTED=int(os.getenv("SENTINEL_MAX_EXTRACTED_MB", "8")) * 1024 * 1024,
        MAX_FILES=int(os.getenv("SENTINEL_MAX_FILES", "50")),
        RETENTION_HOURS=float(os.getenv("SENTINEL_RETENTION_HOURS", "24")),
        WORKERS=int(os.getenv("SENTINEL_WORKERS", "2")),
        QUEUE_SIZE=int(os.getenv("SENTINEL_QUEUE_SIZE", "4")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SENTINEL_COOKIE_SECURE", "false").lower() == "true",
    )
    if config:
        app.config.update(config)
    if production and (not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32):
        raise RuntimeError("Production requires a SECRET_KEY of at least 32 characters")
    if (
        app.config["RETENTION_HOURS"] <= 0
        or app.config["WORKERS"] < 1
        or app.config["QUEUE_SIZE"] < 0
    ):
        raise ValueError("Invalid retention or worker configuration")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    data = Path(app.config["DATA_DIR"])
    store = ResultStore(data / "results.sqlite3", app.config["RETENTION_HOURS"])
    kwargs = {"scan": app.config["SCAN_FUNCTION"]} if "SCAN_FUNCTION" in app.config else {}
    jobs = JobService(
        store,
        app.config.get("SCANNER_CONFIG", ScannerConfig.from_env()),
        app.config["WORKERS"],
        app.config["QUEUE_SIZE"],
        **kwargs,
    )
    app.extensions.update(
        sentinel_store=store,
        sentinel_jobs=jobs,
        sentinel_upload_policy=UploadPolicy(
            app.config["MAX_CONTENT_LENGTH"], app.config["MAX_EXTRACTED"], app.config["MAX_FILES"]
        ),
    )
    from sentinel.blueprints.api import api
    from sentinel.blueprints.web import web

    app.register_blueprint(web)
    app.register_blueprint(api)

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException) -> ResponseReturnValue:
        if request.path.startswith("/api/"):
            return jsonify(error=error.name, message=error.description), error.code or 500
        from flask import render_template

        return render_template(
            "error.html", title=error.name, message=error.description
        ), error.code or 500

    @app.get("/health")
    def health() -> ResponseReturnValue:
        return jsonify(status="ok", version=__version__)

    return app
