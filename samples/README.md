# Educational sample contracts

These are test/demo inputs, not deployment templates. All pin Solidity 0.8.30. Expected rules are verified with Slither 0.11.6 and Contract Radar's registry. `expected.json` specifies required/forbidden findings rather than assuming every incidental style/gas diagnostic is immutable across engine upgrades.

| Contract | Intentional behavior | Expected findings |
|---|---|---|
| Reentrancy.sol | Ether call before balance update | slither/reentrancy-eth; checked return must not trigger SS-008 |
| TxOrigin.sol | tx.origin authorization | SS-006 |
| UncheckedCall.sol | Return value discarded | SS-008 |
| Selfdestruct.sol | Unrestricted selfdestruct recipient | SS-002; Ether transfer remains relevant after Cancun |
| OwnerControls.sol | Mint, blacklist, pause, unbounded fee, implementation control | SS-001, SS-003, SS-004, SS-005, SS-009 |
| PrecisionLoss.sol | Division before multiplication | slither/divide-before-multiply |
| HiddenOwnership.sol | `sync` changes owner; arbitrary delegatecall | SS-010, SS-007; checked call must not trigger SS-008 |
| SafeCounter.sol | Checked arithmetic and emitted event | No custom/material findings; not proof of universal safety |

OwnerControls demonstrates capabilities, not a claim that every authorized mint/pause is malicious. Contract Radar does not prove caps/governance correctness. Integration tests also compile comments/strings/coffee/feed and broken-source fixtures; these are not additional deployable samples.

```sh
contract-radar scan samples/Reentrancy.sol --format md --fail-on high
CONTRACT_RADAR_RUN_INTEGRATION=1 python -m pytest tests/test_integration.py -q
```

The first command deliberately exits 1. Integration needs actual Slither/compiler binaries; first-use installation has a timeout.
