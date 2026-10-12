"""Prepare self-hosted static assets and verified Linux compilers during Vercel builds."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Build deployment assets without runtime compiler downloads."""
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "contract_radar/static", root / "public/static", dirs_exist_ok=True)
    cache_root = root / "deployment/compiler-cache"
    environment = dict(os.environ, VIRTUAL_ENV=str(cache_root))
    subprocess.run(
        [sys.executable, "-m", "solc_select", "install", "0.8.30", "0.8.20", "0.7.6"],
        env=environment,
        check=True,
        timeout=240,
    )


if __name__ == "__main__":
    main()
