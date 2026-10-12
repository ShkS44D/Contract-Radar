"""Generate pinned runtime/dev resolutions with the Windows-only web3 dependency marker."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Regenerate lock files and retain pywin32's original platform requirement."""
    for filename, extras in [
        ("requirements.lock", ["production"]),
        ("requirements-dev.lock", ["production", "dev"]),
    ]:
        args = [
            sys.executable,
            "-m",
            "piptools",
            "compile",
            "pyproject.toml",
            "--strip-extras",
            "--quiet",
            "--output-file",
            filename,
        ]
        for extra in extras:
            args += ["--extra", extra]
        if filename != "requirements.lock":
            args += ["--constraint", "requirements.lock"]
        subprocess.run(args, check=True)
        path = Path(filename)
        lines = path.read_text().splitlines()
        # pip-compile resolves on the host and drops this transitive marker on Windows.
        lines = [
            line + '; sys_platform == "win32"'
            if line.startswith("pywin32==") and ";" not in line
            else line
            for line in lines
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
