"""Vercel entrypoint with read-only bundled compilers and request-bound execution."""

import os
from pathlib import Path

from contract_radar import create_app
from contract_radar.config import ScannerConfig

os.environ.setdefault("CONTRACT_RADAR_ENV", "production")
os.environ.setdefault("CONTRACT_RADAR_COOKIE_SECURE", "true")

app = create_app(
    {
        "EXECUTION_MODE": "request",
        "DATA_DIR": Path("/tmp/contract-radar"),
        "SCANNER_CONFIG": ScannerConfig(
            timeout=120,
            offline=True,
            cache=Path(__file__).resolve().parent / "deployment/compiler-cache/.solc-select",
        ),
    }
)
