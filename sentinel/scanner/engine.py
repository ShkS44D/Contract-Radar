"""Compiler-aware scan orchestration with explicit terminal outcomes."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from filelock import Timeout as LockTimeout

from sentinel.config import ScannerConfig

from .compiler import CompileError, ensure_compiler, resolve_units
from .models import ScanResult, ScanState
from .parser import ReportError, parse_report
from .process import OutputLimitError, ProcessTimeout, run_process
from .source import load_sources

logger = logging.getLogger(__name__)


def scanner_environment(config: ScannerConfig) -> dict[str, str]:
    """Pass only required runtime variables; keep application secrets out of children."""
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    env = {key.upper(): value for key, value in os.environ.items() if key.upper() in allowed}
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["SOLC_SELECT_DIR"] = str(config.cache.resolve())
    # solc-select 1.2 derives its cache from VIRTUAL_ENV, not SOLC_SELECT_DIR.
    if config.cache.name != ".solc-select":
        raise ValueError("Compiler cache must be named .solc-select")
    env["VIRTUAL_ENV"] = str(config.cache.resolve().parent)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def scan_project(
    root: Path, scan_id: str, filename: str, config: ScannerConfig | None = None
) -> ScanResult:
    """Analyze validated local sources, returning failures instead of empty clean reports."""
    config = config or ScannerConfig.from_env()
    started = time.monotonic()
    result = ScanResult(scan_id, ScanState.RUNNING, filename)
    diagnostic = ""
    try:
        sources = load_sources(root)
        units = resolve_units(sources, default=config.default_compiler)
        result.metadata.update(
            compilers={unit.entry: unit.compiler for unit in units},
            warnings=[warning for unit in units for warning in unit.warnings],
            sloc=sum(source.sloc for source in sources.values()),
            file_count=len(sources),
        )
        env = scanner_environment(config)
        deadline = time.monotonic() + config.timeout
        for unit in units:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProcessTimeout("Scan deadline exceeded")
            ensure_compiler(
                unit.compiler,
                cache=config.cache,
                env=env,
                timeout=min(config.compiler_timeout, remaining),
                offline=config.offline,
            )
            child_env = dict(env, SOLC_VERSION=unit.compiler)
            with tempfile.TemporaryDirectory(prefix="sentinel-engine-") as temporary:
                output = Path(temporary) / "slither.json"
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProcessTimeout("Scan deadline exceeded during compiler setup")
                process = run_process(
                    [sys.executable, "-m", "sentinel.scanner.worker", unit.entry, str(output)],
                    cwd=root,
                    env=child_env,
                    timeout=remaining,
                )
                diagnostic = process.stderr[-6000:]
                if not output.is_file():
                    raise ReportError(f"Slither did not write a report (exit {process.returncode})")
                if output.stat().st_size > 20_000_000:
                    raise ReportError("Slither report exceeded size limit")
                data = json.loads(output.read_text(encoding="utf-8"))
                findings = parse_report(data, sources)
                if process.returncode != 0:
                    raise ReportError(f"Slither process failed with exit {process.returncode}")
                result.findings.extend(findings)
                result.metadata["slither_version"] = data["sentinel_metadata"]["slither_version"]
        result.state = ScanState.COMPLETED
    except (ProcessTimeout, LockTimeout) as exc:
        result.state = ScanState.TIMEOUT
        result.diagnostics = str(exc)
    except CompileError as exc:
        result.state = ScanState.COMPILE_ERROR
        result.diagnostics = str(exc)
    except (OSError, ValueError, KeyError, TypeError, OutputLimitError) as exc:
        result.state = ScanState.ENGINE_ERROR
        result.diagnostics = f"{type(exc).__name__}: {exc}"
        logger.exception("Scan %s failed", scan_id)
    if result.state != ScanState.COMPLETED:
        result.findings = []
    if result.state != ScanState.COMPLETED:
        result.diagnostics = (
            (result.diagnostics + "\n" + diagnostic).strip().replace(str(root), "<project>")[:6000]
        )
    result.metadata["duration_seconds"] = round(time.monotonic() - started, 3)
    return result
