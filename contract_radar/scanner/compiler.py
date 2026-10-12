"""Deterministic, per-compilation-unit compiler resolution."""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from filelock import FileLock
from semantic_version import NpmSpec, Version

from .process import run_process
from .source import Source, mask_source

# Deliberately bounded, tested release catalog; no floating network version lookup.
SUPPORTED_VERSIONS = tuple(
    [f"0.4.{v}" for v in range(11, 27)]
    + [f"0.5.{v}" for v in range(0, 18)]
    + [f"0.6.{v}" for v in range(0, 13)]
    + [f"0.7.{v}" for v in range(0, 7)]
    + [f"0.8.{v}" for v in range(0, 31)]
)


class CompileError(ValueError):
    """Source ranges/imports cannot be compiled under the supported policy."""


@dataclass(frozen=True)
class CompilationUnit:
    """One source entry and its reachable import graph."""

    entry: str
    files: tuple[str, ...]
    compiler: str
    warnings: tuple[str, ...] = ()


def pragma_specs(source: Source) -> list[NpmSpec]:
    """Parse stable Solidity constraints and reject unsupported range syntax."""
    specs = []
    for match in re.finditer(r"\bpragma\s+solidity\s+([^;]+);", source.masked):
        value = match[1].strip()
        # npm grammar implements Solidity's caret/OR/comparator conventions.
        value = re.sub(r"([<>=^~]+)\s+(?=\d)", r"\1", value)
        if re.search(r"[^\d\s.<>=^~|*xX-]", value):
            raise CompileError(f"Unsupported pragma in {source.file}: {value}")
        try:
            specs.append(NpmSpec(value))
        except ValueError as exc:
            raise CompileError(f"Invalid pragma in {source.file}: {value}") from exc
    return specs


def resolve_units(sources: dict[str, Source], *, default: str = "0.8.30") -> list[CompilationUnit]:
    """Resolve import closures, allowing independent roots to use different compilers."""
    if not sources:
        raise CompileError("No Solidity sources found")
    graph: dict[str, list[str]] = {}
    for name, source in sources.items():
        imports = re.findall(
            r"\bimport\s+(?:[^;]*?\bfrom\s+)?[\"']([^\"']+)[\"']\s*;",
            mask_source(source.text, strings=False),
        )
        graph[name] = []
        for imported in imports:
            path = PurePosixPath(imported)
            if path.is_absolute() or "\\" in imported or ":" in imported:
                raise CompileError(f"Unsafe import in {name}: {imported}")
            base = PurePosixPath(name).parent if imported.startswith(".") else PurePosixPath()
            normalized = os.path.normpath(str(base / path)).replace("\\", "/")
            if normalized.startswith("../") or normalized not in sources:
                raise CompileError(f"Missing or external import in {name}: {imported}")
            graph[name].append(normalized)
    imported_files = {child for children in graph.values() for child in children}
    entries = sorted(set(sources) - imported_files)
    covered: set[str] = set()
    units = []
    # Uncovered files handle cycles, instead of silently omitting them.
    for entry in entries + sorted(imported_files):
        if entry in covered:
            continue
        reachable: set[str] = set()
        pending = [entry]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(graph[current])
        specs = [spec for name in sorted(reachable) for spec in pragma_specs(sources[name])]
        candidates = [
            version
            for version in SUPPORTED_VERSIONS
            if all(spec.match(Version(version)) for spec in specs)
        ]
        if not candidates:
            raise CompileError(f"No supported compiler satisfies imports of {entry}")
        compiler = candidates[-1] if specs else default
        if compiler not in SUPPORTED_VERSIONS:
            raise CompileError("Default compiler is outside the supported catalog")
        warnings = tuple(
            f"{name}: missing Solidity pragma; selected {compiler}"
            for name in sorted(reachable)
            if not pragma_specs(sources[name])
        )
        units.append(CompilationUnit(entry, tuple(sorted(reachable)), compiler, warnings))
        covered.update(reachable)
    return units


def ensure_compiler(
    version: str, *, cache: Path, env: dict[str, str], timeout: float, offline: bool
) -> None:
    """Install a compiler once without mutating solc-select's global selection."""
    artifact = cache / "artifacts" / f"solc-{version}" / f"solc-{version}"
    if offline and artifact.is_file():
        return
    if offline:
        raise CompileError(f"Compiler {version} is unavailable in offline mode")
    cache.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with FileLock(str(cache / "install.lock"), timeout=max(0.1, timeout)):
        artifact = cache / "artifacts" / f"solc-{version}" / f"solc-{version}"
        if artifact.is_file():
            return
        if offline:
            raise CompileError(f"Compiler {version} is unavailable in offline mode")
        result = run_process(
            [sys.executable, "-m", "solc_select", "install", version],
            cwd=cache,
            env=env,
            timeout=max(0.01, timeout - (time.monotonic() - started)),
        )
        if result.returncode or not artifact.is_file():
            raise CompileError(
                f"Compiler installation failed for {version}: {result.stderr[-1500:]}"
            )
