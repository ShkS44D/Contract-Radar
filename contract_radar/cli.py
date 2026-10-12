"""Command-line interface for source scanning and CI policy enforcement."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from .scanner.engine import scan_project
from .scanner.models import ScanState, Severity
from .services.exports import EXPORTERS
from .services.uploads import UploadError, UploadPolicy, prepare_path


def main(argv: list[str] | None = None) -> int:
    """Run a scan: 0 success, 1 finding threshold, 2 input/engine failure."""
    parser = argparse.ArgumentParser(
        prog="contract-radar", description="Solidity static analysis (not a manual audit)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Scan a .sol file, .zip archive, or source directory")
    scan.add_argument("path", type=Path)
    scan.add_argument("--format", choices=["json", "sarif", "md"], default="json")
    scan.add_argument("--fail-on", choices=[s.value for s in Severity])
    scan.add_argument("--output", "-o", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        with tempfile.TemporaryDirectory(prefix="contract_radar-cli-") as temporary:
            root = prepare_path(args.path.resolve(), Path(temporary), UploadPolicy())
            try:
                result = scan_project(root, str(uuid.uuid4()), args.path.name)
            finally:
                shutil.rmtree(root, ignore_errors=True)
            payload = EXPORTERS[args.format][0](result)
            if args.output:
                args.output.write_bytes(payload)
            else:
                sys.stdout.write(payload.decode("utf-8") + "\n")
            if result.state != ScanState.COMPLETED:
                return 2
            if args.fail_on and any(
                f.severity.rank <= Severity(args.fail_on).rank for f in result.findings
            ):
                return 1
            return 0
    except (OSError, UploadError) as exc:
        logging.error("Cannot scan: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
