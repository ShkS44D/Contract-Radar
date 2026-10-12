"""Isolated Slither CLI runner; invoked only by the parent engine."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Write a Slither envelope and fail explicitly on CLI errors."""
    entry, output = sys.argv[1:3]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "slither",
            entry,
            "--json",
            output,
            "--fail-none",
            "--compile-force-framework",
            "solc",
        ],
        check=False,
    )
    path = Path(output)
    if not path.is_file():
        return completed.returncode or 2
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sentinel_metadata"] = {
        "slither_version": importlib.metadata.version("slither-analyzer"),
        "exit_code": completed.returncode,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
