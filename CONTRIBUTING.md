# Contributing

Read [architecture](docs/ARCHITECTURE.md), [detector evidence](docs/DETECTORS.md), and [scoring](docs/SCORING.md). Keep changes small/readable. Public functions/classes need docstrings and type hints. Never turn failed analysis into successful empty findings or label a capability an exploit without evidence.

## Setup and checks

Create an external Python 3.11/3.12 venv using README instructions:

```sh
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
python -m ruff check contract_radar tests scripts app.py
python -m ruff format --check contract_radar tests scripts app.py
python -m mypy
python -m pytest --cov=contract_radar.scanner --cov-report=term-missing
CONTRACT_RADAR_RUN_INTEGRATION=1 python -m pytest tests/test_integration.py -q
docker compose config --quiet
docker compose build
docker compose up -d --wait
```

PowerShell: set `$env:CONTRACT_RADAR_RUN_INTEGRATION='1'` before pytest and remove it afterward. Without activation, invoke your external venv's Python. Gunicorn is used only in the Linux container; Windows development uses `app.py`.

Coverage minimum is 80% of the scanner, including the adapter. Real integrations require binaries and possibly HTTPS downloads. Explain checks you could not run; configuration validation is not Docker/CI runtime verification. UI changes need real upload/error flows, filters/search/details, exports, desktop/mobile/keyboard checks, and healthy console/CSP. PDF changes need rendered inspection of every page.

## Detector changes

Use typed AST/IR facts; lexical masking must preserve offsets. Every rule needs positive/negative tests, exact locations, plain-English evidence, and concrete fixes. Include comment/string/unrelated-identifier regressions and a real sample where appropriate. Curate taxonomy/equivalences; never guess SWC/CWE IDs. Preserve distinct occurrences and avoid duplicate penalties.

Update samples/expected.json after reviewing pinned-engine output. Prefer required/forbidden rules over brittle snapshots. Document heuristic limits; confidence is independent of severity.

## Dependencies and pull requests

Direct/tool dependencies are pinned in pyproject.toml. Regenerate locks with `python scripts/lock.py`; review both. The helper retains pywin32's Windows-only marker. Keep secrets, venvs, uploads, reports, database state, and QA captures out of Git.

Use conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `build:`). PRs should explain the concrete issue, behavior, evidence, tests, and limitations. Avoid unrelated formatting/dependency churn. Report security issues through [SECURITY.md](SECURITY.md).
