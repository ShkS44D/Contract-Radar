"""Container bootstrap with a persisted private secret and one Gunicorn worker."""

import os
import secrets
from pathlib import Path


def main() -> None:
    """Start production serving; auto-provision a volume-local secret for Compose."""
    data = Path(os.getenv("CONTRACT_RADAR_DATA_DIR", "/data"))
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not os.getenv("SECRET_KEY"):
        secret = data / ".secret-key"
        if not secret.exists():
            descriptor = os.open(secret, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(secrets.token_hex(32))
        os.environ["SECRET_KEY"] = secret.read_text().strip()
    os.environ["CONTRACT_RADAR_ENV"] = "production"
    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "contract_radar:create_app()",
            "--bind",
            "0.0.0.0:5000",
            "--workers",
            "1",
            "--threads",
            "4",
            "--timeout",
            "180",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
        ],
    )


if __name__ == "__main__":
    main()
