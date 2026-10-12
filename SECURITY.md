# Security policy

## Supported version

The v2.x line is supported. v1's unreliable failure handling makes it unsuitable for security decisions.

## Reporting

Use [GitHub private vulnerability reporting](https://github.com/ShkS44D/Solidity-Sentinel/security/advisories/new) if enabled. The maintainer must enable it before inviting private reports. Do not publish secrets, confidential source, or weaponized exploits in public issues. If private reporting is unavailable, request a private contact method without disclosing vulnerability details.

Include version/commit, environment, minimal non-confidential reproduction, impact, expected behavior, and any mitigation. Distinguish vulnerabilities in Sentinel from findings in uploaded contracts. No guaranteed SLA or bug bounty is offered.

## Boundaries

Static analysis is not a manual audit. A clean scan/high score does not establish safety. Failed/unfinished scans are unscored. Compiler/engine bugs, assembly, sophisticated authorization, and dependencies can limit results.

UUID report URLs are bearer links and contain snippets. Keep links private. Retention is logical database deletion; backups, logs, copies, and filesystem recovery are outside it. Sources are temporary; cleanup failures are explicit errors.

Default deployment is loopback/local or a trusted small-team service. Public hosting requires authentication, stronger worker/network isolation, durable queues, trusted proxy handling, and disk quotas. Non-root Docker is not a complete hostile-code sandbox. Use HTTPS/secure cookies remotely. Read [HARDENING](docs/HARDENING.md) and [verification limits](docs/VERIFICATION.md).
