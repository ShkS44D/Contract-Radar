"""Reject non-UTF-8 tracked text before package metadata is installed."""

import subprocess
from pathlib import Path

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".lock",
    ".yml",
    ".yaml",
    ".html",
    ".css",
    ".js",
    ".json",
    ".svg",
    ".sol",
    ".txt",
    ".example",
}
TEXT_NAMES = {
    "Makefile",
    "LICENSE",
    ".gitignore",
    ".dockerignore",
    ".vercelignore",
    ".python-version",
}


def main() -> int:
    """Validate tracked text without scanning generated data or local secrets."""
    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root, timeout=10)
    invalid = []
    for raw_name in files.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode("utf-8")
        path = root / name
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            invalid.append(f"{name}: invalid UTF-8 at byte {error.start}")
    if invalid:
        raise SystemExit("\n".join(invalid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
