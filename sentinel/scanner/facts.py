"""Small typed AST/IR projection consumed by independently testable detectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NodeFact:
    """Evidence at an exact statement range from Slither's control-flow graph."""

    start: int
    end: int
    expression: str = ""
    conditional: bool = False
    variables: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()
    unchecked: bool = False


@dataclass(frozen=True)
class FunctionFact:
    """Function declaration and semantic writes/calls/authorization evidence."""

    file: str
    name: str
    start: int
    end: int
    visibility: str = "public"
    owner_guard: bool = False
    writes: tuple[str, ...] = ()
    internal_calls: tuple[str, ...] = ()
    nodes: tuple[NodeFact, ...] = ()
    constructor: bool = False


@dataclass
class AnalysisFacts:
    """Serializable AST facts for all locally compiled contracts."""

    functions: list[FunctionFact] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisFacts:
        """Decode worker output, preserving tuple-valued immutable facts."""
        functions = []
        for item in data.get("functions", []):
            values = dict(item)
            values["nodes"] = tuple(
                NodeFact(
                    **dict(node, variables=tuple(node["variables"]), calls=tuple(node["calls"]))
                )
                for node in values.get("nodes", [])
            )
            values["writes"] = tuple(values.get("writes", []))
            values["internal_calls"] = tuple(values.get("internal_calls", []))
            functions.append(FunctionFact(**values))
        return cls(functions, list(data.get("contracts", [])))
