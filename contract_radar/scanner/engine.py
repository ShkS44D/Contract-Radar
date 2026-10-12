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

from contract_radar.config import ScannerConfig

from .compiler import CompileError, ensure_compiler, resolve_units
from .detectors import deduplicate, run_detectors
from .facts import AnalysisFacts
from .models import ScanResult, ScanState
from .parser import ReportError, parse_report
from .process import ProcessTimeout, run_process
from .scoring import apply_score
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
        facts = AnalysisFacts()
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
            with tempfile.TemporaryDirectory(prefix="contract_radar-engine-") as temporary:
                output = Path(temporary) / "slither.json"
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProcessTimeout("Scan deadline exceeded during compiler setup")
                process = run_process(
                    [
                        sys.executable,
                        "-m",
                        "contract_radar.scanner.worker",
                        unit.entry,
                        str(output),
                    ],
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
                if "contract_radar_facts" not in data:
                    raise ReportError("Slither worker omitted compiler-backed facts")
                unit_facts = AnalysisFacts.from_dict(data["contract_radar_facts"])
                facts.functions.extend(unit_facts.functions)
                facts.contracts.extend(unit_facts.contracts)
                result.metadata["slither_version"] = data["contract_radar_metadata"][
                    "slither_version"
                ]
        if not facts.contracts:
            raise CompileError("No contract, interface, or library declarations could be analyzed")
        result.findings = deduplicate(result.findings + run_detectors(sources, facts))
        if len(sources) == 1 and filename.lower().endswith(".sol"):
            # Keep source identity stable despite random physical upload filenames.
            for finding in result.findings:
                finding.description = finding.description.replace(finding.file, filename)
                finding.file = filename
                finding.id = ""
                finding.__post_init__()
            result.metadata["compilers"] = {filename: units[0].compiler}
        result.metadata["contract_count"] = len(set(facts.contracts))
        result.metadata["function_count"] = len(
            {
                (f.file, f.name, f.start, f.end)
                for f in facts.functions
                if not f.constructor and not f.modifier
            }
        )
        result.state = ScanState.COMPLETED
        apply_score(result)
    except (ProcessTimeout, LockTimeout) as exc:
        result.state = ScanState.TIMEOUT
        result.diagnostics = str(exc)
    except CompileError as exc:
        result.state = ScanState.COMPILE_ERROR
        result.diagnostics = str(exc)
    except Exception as exc:
        result.state = ScanState.ENGINE_ERROR
        result.diagnostics = f"{type(exc).__name__}: {exc}"
        logger.exception("Scan %s failed", scan_id)
    if result.state != ScanState.COMPLETED:
        result.findings = []
        result.score = result.grade = result.risk = None
        result.breakdown = []
        result.diagnostics = (
            (result.diagnostics + "\n" + diagnostic).strip().replace(str(root), "<project>")[:6000]
        )
        for private in sorted(
            {
                str(Path.home()),
                str(config.cache),
                sys.prefix,
                sys.base_prefix,
                str(Path(__file__).resolve().parents[2]),
            },
            key=len,
            reverse=True,
        ):
            result.diagnostics = result.diagnostics.replace(private, "<runtime>").replace(
                private.replace("\\", "/"), "<runtime>"
            )
    result.metadata["duration_seconds"] = round(time.monotonic() - started, 3)
    return result
