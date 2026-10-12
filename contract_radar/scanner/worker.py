"""Isolated Slither CLI runner; invoked only by the parent engine."""

from __future__ import annotations

import importlib.metadata
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from contract_radar.scanner.facts import AnalysisFacts, FunctionFact, NodeFact


def collect_facts(entry: str) -> AnalysisFacts:
    """Project Slither AST/IR into a small serializable detector interface."""
    from slither.core.declarations.modifier import Modifier
    from slither.detectors.operations.unchecked_low_level_return_values import UncheckedLowLevel
    from slither.slither import Slither
    from slither.slithir.operations import LowLevelCall, SolidityCall

    slither = Slither(entry, compile_force_framework="solc")
    root = Path.cwd().resolve()
    facts = AnalysisFacts()
    seen = set()
    for contract in slither.contracts:
        file = Path(contract.source_mapping.filename.absolute).resolve()
        if not file.is_relative_to(root):
            continue
        facts.contracts.append(f"{file.relative_to(root).as_posix()}:{contract.name}")
        for function in contract.functions_and_modifiers:
            mapping = function.source_mapping
            file = Path(mapping.filename.absolute).resolve()
            key = (str(file), function.full_name, tuple(mapping.lines))
            if key in seen or not file.is_relative_to(root) or not mapping.lines:
                continue
            seen.add(key)
            nodes = []
            unused = set(UncheckedLowLevel.detect_unused_return_values(function))
            guards = list(function.nodes) + [
                n for modifier in function.modifiers for n in modifier.nodes
            ]
            owner_guard = any(
                (n.contains_if() or n.contains_require_or_assert())
                and re.search(r"\bmsg\.sender\b", str(n.expression))
                and re.search(r"\b_?(owner|admin)\b", str(n.expression), re.I)
                and "==" in str(n.expression)
                for n in guards
            )
            for node in function.nodes:
                if not node.source_mapping.lines:
                    continue
                calls = []
                for ir in node.irs:
                    if isinstance(ir, LowLevelCall):
                        calls.append(str(ir.function_name))
                    elif isinstance(ir, SolidityCall):
                        calls.append(str(ir.function.name))
                nodes.append(
                    NodeFact(
                        min(node.source_mapping.lines),
                        max(node.source_mapping.lines),
                        str(node.expression or ""),
                        bool(node.contains_if() or node.contains_require_or_assert()),
                        tuple(str(v.name) for v in node.variables_read),
                        tuple(calls),
                        node in unused,
                    )
                )
            facts.functions.append(
                FunctionFact(
                    file.relative_to(root).as_posix(),
                    function.name,
                    min(mapping.lines),
                    max(mapping.lines),
                    function.visibility,
                    bool(owner_guard),
                    tuple(v.name for v in function.all_state_variables_written()),
                    tuple(
                        call.function.name
                        for call in function.all_internal_calls()
                        if getattr(call, "function", None) is not None
                    ),
                    tuple(nodes),
                    bool(function.is_constructor),
                    isinstance(function, Modifier),
                )
            )
    return facts


def main() -> int:
    """Write a Slither envelope and fail explicitly on CLI errors."""
    entry, output = sys.argv[1:3]
    from crytic_compile.platform.exceptions import InvalidCompilation
    from slither.exceptions import SlitherError

    try:
        facts = collect_facts(entry)
    except InvalidCompilation as exc:
        Path(output).write_text(json.dumps({"success": False, "error": str(exc)}), encoding="utf-8")
        return 2
    except SlitherError as exc:
        if not str(exc).startswith("Invalid compilation:"):
            raise
        Path(output).write_text(json.dumps({"success": False, "error": str(exc)}), encoding="utf-8")
        return 2
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
    data["contract_radar_metadata"] = {
        "slither_version": importlib.metadata.version("slither-analyzer"),
        "exit_code": completed.returncode,
    }
    if data.get("success") and completed.returncode == 0:
        # Slither omits detectors when there are zero findings. Normalize only after
        # independently compiling facts and validating the CLI success/exit status.
        if isinstance(data.get("results"), dict):
            data["results"].setdefault("detectors", [])
        data["contract_radar_facts"] = asdict(facts)
    path.write_text(json.dumps(data), encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
