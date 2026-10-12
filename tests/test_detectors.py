"""Every custom detector has both positive and negative evidence cases."""

from dataclasses import replace

import pytest

from sentinel.scanner.detectors import (
    DETECTORS,
    BlacklistDetector,
    DelegatecallDetector,
    FeeDetector,
    HiddenOwnershipDetector,
    MintDetector,
    OldCompilerDetector,
    OwnerPowerDetector,
    PauseDetector,
    SelfdestructDetector,
    TxOriginDetector,
    UncheckedCallDetector,
    deduplicate,
    identifier_words,
    run_detectors,
)
from sentinel.scanner.facts import AnalysisFacts, FunctionFact, NodeFact
from sentinel.scanner.models import Confidence, Finding, Severity
from sentinel.scanner.source import Source

SOURCES = {
    "A.sol": Source("A.sol", "pragma solidity ^0.8.0;\ncontract A {\nfunction f() public {}\n}\n")
}
BASE = FunctionFact("A.sol", "f", 3, 3)


@pytest.mark.parametrize(
    "detector,positive,negative",
    [
        (
            MintDetector,
            replace(BASE, name="mint", writes=("totalSupply",)),
            replace(BASE, name="mintCoffee", writes=("coffee",)),
        ),
        (
            SelfdestructDetector,
            replace(BASE, nodes=(NodeFact(3, 3, calls=("selfdestruct(address)",)),)),
            replace(BASE, name="selfdestructHelper"),
        ),
        (
            BlacklistDetector,
            replace(
                BASE,
                writes=("blacklist",),
                nodes=(NodeFact(3, 3, conditional=True, variables=("blacklist",)),),
            ),
            replace(BASE, writes=("blacklist",)),
        ),
        (
            PauseDetector,
            replace(
                BASE,
                writes=("paused",),
                nodes=(NodeFact(3, 3, conditional=True, variables=("paused",)),),
            ),
            replace(BASE, name="pause"),
        ),
        (
            FeeDetector,
            replace(BASE, owner_guard=True, writes=("taxFee",)),
            replace(BASE, owner_guard=True, writes=("coffee", "feed")),
        ),
        (
            TxOriginDetector,
            replace(
                BASE, nodes=(NodeFact(3, 3, conditional=True, variables=("tx.origin", "owner")),)
            ),
            replace(
                BASE,
                nodes=(NodeFact(3, 3, conditional=True, variables=("tx.origin", "msg.sender")),),
            ),
        ),
        (
            DelegatecallDetector,
            replace(BASE, nodes=(NodeFact(3, 3, calls=("delegatecall",)),)),
            replace(BASE, name="delegatecallHelper"),
        ),
        (
            UncheckedCallDetector,
            replace(BASE, nodes=(NodeFact(3, 3, calls=("call",), unchecked=True),)),
            replace(BASE, nodes=(NodeFact(3, 3, calls=("call",)),)),
        ),
        (
            OwnerPowerDetector,
            replace(BASE, owner_guard=True, writes=("implementation",)),
            replace(BASE, owner_guard=True, writes=("displayName",)),
        ),
        (
            HiddenOwnershipDetector,
            replace(BASE, name="sync", writes=("owner",)),
            replace(BASE, name="transferOwnership", writes=("owner",)),
        ),
    ],
)
def test_detector_true_and_false_positive(detector, positive, negative):
    found = detector().detect(SOURCES, AnalysisFacts([positive]))
    assert len(found) == 1
    assert found[0].rule_id == detector.id
    assert found[0].line_start == 3 and found[0].file == "A.sol"
    assert found[0].snippet and found[0].remediation
    assert not detector().detect(SOURCES, AnalysisFacts([negative]))
    assert not detector().detect(SOURCES, AnalysisFacts([replace(positive, constructor=True)]))
    assert not detector().detect(SOURCES, AnalysisFacts([replace(positive, file="external.sol")]))


def test_old_compiler_positive_negative_and_comments():
    old = {"A.sol": Source("A.sol", "// pragma solidity ^0.4.0;\npragma solidity >=0.7.0 <0.9.0;")}
    found = OldCompilerDetector().detect(old, AnalysisFacts())
    assert len(found) == 1 and found[0].line_start == 2
    assert not OldCompilerDetector().detect(SOURCES, AnalysisFacts())


def test_comments_strings_and_unrelated_words_do_not_trigger():
    source = Source(
        "A.sol",
        'pragma solidity ^0.8.0;\n// mint selfdestruct blacklist\ncontract Coffee { string label = "pausable tax tx.origin delegatecall"; uint coffee; uint feed; }',
    )
    assert not run_detectors({"A.sol": source}, AnalysisFacts())
    assert identifier_words("coffeeFeed") == {"coffee", "feed"}
    assert identifier_words("setTaxFee") == {"set", "tax", "fee"}
    assert len({d.id for d in DETECTORS}) == len(DETECTORS)


def test_public_mint_call_and_nonpublic_exclusion():
    function = replace(BASE, internal_calls=("_mint(address,uint256)",))
    assert MintDetector().detect(SOURCES, AnalysisFacts([function]))
    assert not MintDetector().detect(
        SOURCES, AnalysisFacts([replace(function, visibility="internal")])
    )


def test_specific_owner_capabilities_are_not_reported_twice():
    function = replace(BASE, owner_guard=True, writes=("taxFee",))
    facts = AnalysisFacts([function])
    assert FeeDetector().detect(SOURCES, facts)
    assert not OwnerPowerDetector().detect(SOURCES, facts)


def test_dedup_retains_provenance_and_distinct_occurrences():
    narrow = Finding(
        "SS-006", "Origin", Severity.HIGH, Confidence.MEDIUM, "why", "fix", "A.sol", 3, 3
    )
    broad = replace(narrow, line_start=2, line_end=4, id="broad", provenance=["slither"])
    distinct = replace(narrow, line_start=10, line_end=10, id="other")
    found = deduplicate([broad, narrow, narrow, distinct])
    assert len(found) == 2
    assert found[0].line_start == 3
    assert found[0].provenance == ["sentinel", "slither"]


def test_facts_roundtrip():
    from dataclasses import asdict

    facts = AnalysisFacts([replace(BASE, nodes=(NodeFact(3, 3, calls=("call",)),))], ["A"])
    assert AnalysisFacts.from_dict(asdict(facts)) == facts
