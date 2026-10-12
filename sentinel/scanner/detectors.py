"""Conservative capability and vulnerability detectors over compiler-backed facts."""

from __future__ import annotations

import re
from typing import ClassVar

from .facts import AnalysisFacts, FunctionFact, NodeFact
from .models import Confidence, Finding, Severity
from .source import Source


def identifier_words(name: str) -> set[str]:
    """Split Solidity snake/camel-case identifiers without substring matching."""
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return {part.lower() for part in re.split(r"[^a-zA-Z0-9]+", expanded) if part}


class Detector:
    """Base contract for source-backed detectors with auditable metadata."""

    id: ClassVar[str]
    title: ClassVar[str]
    severity: ClassVar[Severity]
    description: ClassVar[str]
    remediation: ClassVar[str]
    swc: ClassVar[str | None] = None
    cwe: ClassVar[str | None] = None
    confidence: ClassVar[Confidence] = Confidence.MEDIUM

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        """Return triggering AST nodes; subclasses implement their evidence predicate."""
        raise NotImplementedError

    def detect(self, sources: dict[str, Source], facts: AnalysisFacts) -> list[Finding]:
        """Emit exact locations and escaped-by-consumer source context."""
        findings = []
        for function in facts.functions:
            if function.file not in sources or function.constructor:
                continue
            for node in self.matches(function, facts):
                snippet, first = sources[function.file].context(node.start, node.end)
                findings.append(
                    Finding(
                        self.id,
                        self.title,
                        self.severity,
                        self.confidence,
                        self.description,
                        self.remediation,
                        function.file,
                        node.start,
                        node.end,
                        snippet,
                        first,
                        self.swc,
                        self.cwe,
                    )
                )
        return findings


def declaration(function: FunctionFact) -> list[NodeFact]:
    """Use the declaration line for function-level capability evidence."""
    return [NodeFact(function.start, function.start)]


class MintDetector(Detector):
    """Detect public supply mutation backed by state writes or mint calls."""

    id = "SS-001"
    title = "Externally reachable mint capability"
    severity = Severity.MEDIUM
    description = "An external function can reach mint logic or mutate supply. This is a supply-control capability; caps and governance require manual review."
    remediation = "Enforce a supply cap and narrow authorization; use timelocked governance for privileged issuance."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        named = "mint" in identifier_words(function.name)
        supply_write = any("supply" in identifier_words(v) for v in function.writes)
        mint_call = any(
            "mint" in identifier_words(name.split("(")[0]) for name in function.internal_calls
        )
        if function.visibility in {"public", "external"} and (
            mint_call or (named and supply_write)
        ):
            return declaration(function)
        return []


class SelfdestructDetector(Detector):
    """Detect actual selfdestruct IR calls, independent of identifier names."""

    id = "SS-002"
    title = "Selfdestruct operation"
    severity = Severity.HIGH
    confidence = Confidence.HIGH
    swc = "106"
    cwe = "284"
    description = "The contract executes selfdestruct, transferring its Ether balance. After Cancun, code/storage deletion normally occurs only when called in the creation transaction. Reachability and recipient control require review."
    remediation = "Remove selfdestruct or strictly constrain access and recipients; document the intended EVM-fork behavior."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        return [
            n
            for n in function.nodes
            if any(c.startswith(("selfdestruct(", "suicide(")) for c in n.calls)
        ]


class BlacklistDetector(Detector):
    """Detect mutable blocklist state used in executable conditions."""

    id = "SS-003"
    title = "Mutable blacklist or blocklist"
    severity = Severity.MEDIUM
    description = "An externally reachable function changes blacklist state read by a condition. Administrators may restrict participation; this is a centralization capability, not proof of abuse."
    remediation = "Document restrictions, constrain roles, and use governance delays and emitted events for list changes."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        names = {
            v
            for v in function.writes
            if identifier_words(v) & {"blacklist", "blocklist", "blacklisted", "blocklisted"}
        }
        used = any(
            n.conditional and names.intersection(n.variables)
            for f in facts.functions
            for n in f.nodes
        )
        return (
            declaration(function)
            if names and used and function.visibility in {"public", "external"}
            else []
        )


class PauseDetector(Detector):
    """Detect public mutation of pause state used to gate execution."""

    id = "SS-004"
    title = "Pause control capability"
    severity = Severity.INFO
    description = "An external function changes pause state used by a condition. Pausing can be a useful emergency control; review who can stop and resume operations."
    remediation = (
        "Separate pause/resume roles, emit events, and document recovery and governance procedures."
    )

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        names = {v for v in function.writes if identifier_words(v) & {"pause", "paused"}}
        used = any(
            n.conditional and names.intersection(n.variables)
            for f in facts.functions
            for n in f.nodes
        )
        return (
            declaration(function)
            if names and used and function.visibility in {"public", "external"}
            else []
        )


class FeeDetector(Detector):
    """Detect owner-guarded writes to fee/tax state, not fee substrings."""

    id = "SS-005"
    title = "Owner-controlled fee or tax"
    severity = Severity.MEDIUM
    description = "An owner-authorized function changes fee/tax state. This creates pricing discretion; review on-chain caps and whether users can exit before changes."
    remediation = "Enforce explicit fee caps, emit changes, and apply a timelock before new rates take effect."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        fee_write = any(
            identifier_words(v) & {"fee", "fees", "tax", "deduction"} for v in function.writes
        )
        return (
            declaration(function)
            if function.owner_guard and fee_write and function.visibility in {"public", "external"}
            else []
        )


class TxOriginDetector(Detector):
    """Detect origin checks in authorization-like conditions."""

    id = "SS-006"
    title = "tx.origin used in a sensitive condition"
    severity = Severity.HIGH
    swc = "115"
    cwe = "346"
    description = "A condition depends on tx.origin instead of the immediate caller. A malicious intermediary may satisfy this check when a trusted wallet interacts with it."
    remediation = "Use msg.sender and explicit roles for authorization; test calls through an intermediary contract."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        return [
            n
            for n in function.nodes
            if n.conditional and "tx.origin" in n.variables and "msg.sender" not in n.variables
        ]


class DelegatecallDetector(Detector):
    """Flag executable delegatecalls for target and storage-layout review."""

    id = "SS-007"
    title = "Delegatecall trust boundary"
    severity = Severity.MEDIUM
    swc = "112"
    cwe = "829"
    description = "Delegatecall executes another contract's code using this contract's storage and authority. Its presence requires target, upgrade authorization, and storage-layout review; it does not alone prove an untrusted target."
    remediation = "Constrain targets to reviewed implementations, protect upgrades, and verify storage layout compatibility."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        return [n for n in function.nodes if "delegatecall" in n.calls]


class UncheckedCallDetector(Detector):
    """Reuse Slither IR return-value evidence at exact call sites."""

    id = "SS-008"
    title = "Unused low-level call result"
    severity = Severity.MEDIUM
    swc = "104"
    cwe = "252"
    description = "The return value of a low-level call is unused in Slither's IR. A failed call may leave the contract in an unintended state. Uses that merely log success still need manual review."
    remediation = "Capture the success boolean and revert on failure, or implement an explicit, tested failure-recovery path."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        return [n for n in function.nodes if n.unchecked]


class OwnerPowerDetector(Detector):
    """Surface consequential owner writes without labeling every onlyOwner function."""

    id = "SS-009"
    title = "Sensitive owner-controlled state"
    severity = Severity.MEDIUM
    description = "An owner-authorized external function changes sensitive supply, restriction, pricing, or implementation state. Authorization is present, but governance and bounds determine the centralization risk."
    remediation = "Bound changes, emit events, and consider multisignature authorization and timelocks for consequential powers."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        sensitive = {
            "supply",
            "blacklist",
            "blocklist",
            "blacklisted",
            "fee",
            "tax",
            "implementation",
        }
        writes = any(identifier_words(v) & sensitive for v in function.writes)
        return (
            declaration(function)
            if function.owner_guard and writes and function.visibility in {"public", "external"}
            else []
        )


class HiddenOwnershipDetector(Detector):
    """Identify ownership writes outside constructors and conventional ownership APIs."""

    id = "SS-010"
    title = "Unexpected ownership mutation"
    severity = Severity.HIGH
    cwe = "284"
    description = "An externally reachable function changes owner/admin state outside a conventional transfer/renounce ownership API. Verify authorization and whether this is a concealed control path. Naming alone cannot prove intent."
    remediation = "Centralize ownership changes in an explicit authorized transfer API, validate the new address, and emit ownership events."

    def matches(self, function: FunctionFact, facts: AnalysisFacts) -> list[NodeFact]:
        conventional = {"transferOwnership", "renounceOwnership", "acceptOwnership"}
        changes_owner = any(identifier_words(v) & {"owner", "admin"} for v in function.writes)
        return (
            declaration(function)
            if changes_owner
            and function.name not in conventional
            and function.visibility in {"public", "external"}
            else []
        )


class OldCompilerDetector(Detector):
    """Flag explicit pragma constraints permitting pre-0.8 compilers."""

    id = "SS-011"
    title = "Legacy compiler permitted"
    severity = Severity.LOW
    swc = "102"
    description = "The pragma permits a pre-0.8 compiler without default checked arithmetic. This is a compatibility warning, not proof of an overflow."
    remediation = "Migrate to a reviewed modern compiler and test arithmetic behavior; pin the audited compiler in deployment tooling."

    def detect(self, sources: dict[str, Source], facts: AnalysisFacts) -> list[Finding]:
        from semantic_version import NpmSpec, Version

        from .compiler import SUPPORTED_VERSIONS

        findings = []
        for source in sources.values():
            for match in re.finditer(r"\bpragma\s+solidity\s+([^;]+);", source.masked):
                constraint = re.sub(r"([<>=^~]+)\s+(?=\d)", r"\1", match[1].strip())
                spec = NpmSpec(constraint)
                if any(
                    spec.match(Version(v))
                    for v in SUPPORTED_VERSIONS
                    if Version(v) < Version("0.8.0")
                ):
                    line = source.text.count("\n", 0, match.start()) + 1
                    snippet, first = source.context(line, line)
                    findings.append(
                        Finding(
                            self.id,
                            self.title,
                            self.severity,
                            self.confidence,
                            self.description,
                            self.remediation,
                            source.file,
                            line,
                            line,
                            snippet,
                            first,
                            self.swc,
                        )
                    )
        return findings


DETECTORS: tuple[type[Detector], ...] = (
    MintDetector,
    SelfdestructDetector,
    BlacklistDetector,
    PauseDetector,
    FeeDetector,
    TxOriginDetector,
    DelegatecallDetector,
    UncheckedCallDetector,
    OwnerPowerDetector,
    HiddenOwnershipDetector,
    OldCompilerDetector,
)


def run_detectors(sources: dict[str, Source], facts: AnalysisFacts) -> list[Finding]:
    """Run every registered custom detector."""
    return [finding for detector in DETECTORS for finding in detector().detect(sources, facts)]


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Merge equivalent overlapping locations while retaining the narrowest evidence."""
    merged: list[Finding] = []
    for finding in sorted(findings, key=lambda f: (f.line_end - f.line_start, f.id)):
        existing = next(
            (
                f
                for f in merged
                if f.rule_id == finding.rule_id
                and f.file == finding.file
                and f.line_start <= finding.line_end
                and finding.line_start <= f.line_end
            ),
            None,
        )
        if existing is None:
            merged.append(finding)
        else:
            existing.provenance = sorted(set(existing.provenance + finding.provenance))
            if finding.severity.rank < existing.severity.rank:
                existing.severity = finding.severity
    return sorted(
        merged,
        key=lambda f: (
            f.severity.rank,
            list(Confidence).index(f.confidence),
            f.file,
            f.line_start,
            f.rule_id,
        ),
    )
