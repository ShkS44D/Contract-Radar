"""Environment-derived configuration without implicit debug mode."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScannerConfig:
    """Resource and compiler policy for the scan engine."""

    timeout: float = 120
    compiler_timeout: float = 120
    default_compiler: str = "0.8.30"
    offline: bool = False
    cache: Path = field(
        default_factory=lambda: Path(os.getenv("VIRTUAL_ENV", str(Path.home()))) / ".solc-select"
    )

    @classmethod
    def from_env(cls) -> ScannerConfig:
        """Build scanner policy from explicit environment values."""
        return cls(
            timeout=float(os.getenv("CONTRACT_RADAR_SCAN_TIMEOUT", "120")),
            compiler_timeout=float(os.getenv("CONTRACT_RADAR_COMPILER_TIMEOUT", "120")),
            default_compiler=os.getenv("CONTRACT_RADAR_DEFAULT_COMPILER", "0.8.30"),
            offline=os.getenv("CONTRACT_RADAR_OFFLINE", "false").lower() == "true",
            cache=Path(
                os.getenv(
                    "SOLC_SELECT_DIR",
                    str(Path(os.getenv("VIRTUAL_ENV", str(Path.home()))) / ".solc-select"),
                )
            ),
        )
