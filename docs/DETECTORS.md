# Detector evidence and limitations

Custom detectors operate on a typed projection of Slither's AST/IR, not raw uploaded text. Each class declares its stable ID, title, severity, confidence, explanation, remediation, and optional taxonomy. Findings include exact node/declaration lines and bounded context. Comments and strings are lexically masked for pragma checks; identifiers are split into complete snake/camel-case words.

| ID | Severity | Evidence | SWC / CWE |
|---|---|---|---|
| SS-001 | Medium | Public/external mint call or named mint function writing supply | - |
| SS-002 | High | Actual selfdestruct/suicide IR call | 106 / 284 |
| SS-003 | Medium | Public blacklist mutation plus conditional use | - |
| SS-004 | Info | Public pause-state mutation plus conditional use | - |
| SS-005 | Medium | Owner-authorized fee/tax state mutation | - |
| SS-006 | High | Conditional tx.origin use without msg.sender | 115 / 346 |
| SS-007 | Medium | Actual delegatecall IR operation | 112 / 829 |
| SS-008 | Medium | Slither's unused low-level return-value evidence | 104 / 252 |
| SS-009 | Medium | Owner-authorized sensitive state mutation | - |
| SS-010 | High | Owner/admin mutation outside conventional ownership API | - / 284 |
| SS-011 | Low | Explicit pragma permits a pre-0.8 compiler | 102 / - |

Most custom rules have medium confidence; selfdestruct operation presence has high confidence. Severity expresses potential impact, not certainty of an exploit. Mint/blacklist/pause/fee/delegatecall/owner powers are explicitly described as capabilities requiring review. Caps, timelocks, inheritance, alternate role names, assembly, and sophisticated backdoors are not exhaustively understood. Owner guard evidence currently recognizes an equality between msg.sender and owner/admin in function/modifier conditions; a guard's name alone is insufficient. Merely reading a success boolean is not proof that failure is handled correctly.

Slither's native detectors also run. Known equivalents (tx-origin, unchecked-lowlevel, suicidal, controlled-delegatecall) use canonical custom IDs and overlapping source ranges are merged with retained provenance. Native rules retain `slither/<check>` IDs. Unknown impacts/confidence or missing source locations fail validation rather than silently becoming informational.

Selfdestruct descriptions follow EIP-6780: it still transfers Ether, while deletion normally requires execution in the creation transaction after Cancun. See https://eips.ethereum.org/EIPS/eip-6780.

To add a detector: subclass `Detector` in `sentinel/scanner/detectors.py`, declare all metadata, implement `matches` over facts (or override `detect` for source-level checks), register it in `DETECTORS`, add positive/negative unit tests and a real compiler sample, then update this table and curated taxonomy/equivalence mappings. Never infer vulnerability solely from a function name.
