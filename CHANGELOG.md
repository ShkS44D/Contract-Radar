# Changelog

## [2.0.0] - 2026-10-12

### Added

- Docker-free Vercel deployment adapter with bundled compilers, request-bound execution, private Redis report TTLs, shared admission, and serverless lifecycle tests.

- Typed package/app factory, environment config, blueprints, and shared scanner/service models.
- Import/pragma compiler resolution, bounded installation, per-process compiler choice, deadlines, and process-tree cleanup.
- Eleven custom detectors with precise evidence, confidence, remediation, provenance, and curated taxonomy.
- Diminishing-return confidence scoring, grades/risk labels, and per-rule breakdowns.
- Background jobs, SQLite, UUID reports, retention/restart recovery, stable source fingerprints.
- Safe ZIP projects, CSRF, rate/admission limits, secure headers/CSP, and source cleanup.
- Responsive green/dark reports, API/OpenAPI, CLI, JSON/SARIF/Markdown/PDF exports.
- Eight verified samples, unit/security/export/integration tests, coverage gate, Ruff/mypy, pinned locks, CI, Docker/Compose, Makefile.
- Full technical/contribution/security docs, MIT license, and showcase capture instructions.

### Fixed

- Failed/absent engine output cannot become an empty scored success.
- Comments, strings, coffee/feed, and mere keyword presence no longer drive custom vulnerability claims.
- Upload collisions, Windows line-number drift, duplicate penalties, and silent cleanup errors.
- Successful zero-finding Slither output is normalized only after compiler-backed facts and CLI success.

### Changed

- Removed the obsolete prototype proposal PDF and excluded deployment secrets, provisioned helper skills, and local build leftovers from deployment contexts.

- Rebranded as Contract Radar across package, CLI, configuration, reports, assets, and repository.

- Upload -> report now uses background state/status redirects; `python app.py` remains supported.
- Prototype/unpinned requirements replaced; historical proposal moved into docs.
- Green primary accent with matching green shield favicon.

### Verification limits

Docker build/runtime was blocked by the unavailable local Linux daemon. Compose configuration passed. Remote CI is configured but not yet run; see docs/VERIFICATION.md.

## [1.0.0]

Initial Flask/Slither prototype with six raw-text checks, linear scoring, and dark UI.
