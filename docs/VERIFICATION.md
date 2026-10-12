# v2.0.0 verification record

Date: 2026-10-12. Environment: Windows, Python 3.12.10, pinned Slither 0.11.6 and solc-select 1.2.0, compiler 0.8.30. Runtime/development lock files were generated with pip-tools, installed into an external venv, and passed `pip check`. `scripts/lock.py` retains web3's Windows-only pywin32 platform marker so the locks also support the Linux CI/Docker target.

| Check | Evidence |
|---|---|
| Unit/transport/security/export suite | 108 passed; 10 integration cases are opt-in and skipped in this run |
| Scanner coverage | 90.21%, including the worker adapter; enforced minimum 80% |
| Real engine integrations | 10 passed: eight samples, broken source, and comments/string/coffee/feed regression |
| Owner-control sample after dedup refinement | Passed again; specific mint/fee/list capabilities do not also incur generic owner-power findings |
| Ruff lint and format | Passed |
| mypy scanner | Passed with both Windows and Linux platform settings |
| Real multi-file ZIP | HTTP 202 -> completed; imported project compiled with two contracts |
| Browser flow | Real upload -> loading/polling -> report, filters, search, disclosure, PDF download, error state |
| Browser protections | CSRF-enabled form + strict CSP completed with no console/page errors |
| Viewports | Desktop 1536x1024 and mobile 390x844, no horizontal overflow |
| PDF | Rendered and visually inspected all pages; pypdf verifies pagination/text/links; unsupported Unicode is preserved as escapes |
| SARIF | Completed and failed output validated against the official OASIS 2.1.0 schema |
| Compose configuration | `docker compose config --quiet` passed |
| Packaging | Wheel built successfully with templates/static assets, CLI entry point, and MIT license; no upload/report/venv data included |
| Final smoke check | Fresh app.py startup, real upload/search/filter/export/mobile and broken-source page passed; real high-finding CLI returned 1; safe CLI returned 0 |
| Documentation links | All rendered local Markdown links/images resolve; screenshot/GIF instructions remain explicit placeholders |
| Docker build/runtime | **Not verified:** Docker Desktop start was attempted, but no Linux daemon pipe appeared; `docker compose build` failed before building |
| GitHub Actions | Configured, **not yet run remotely**; requires pushing the branch/commits |
| Local legacy-folder removal | Automatic approval review blocked recursive deletion of `venv/` and `reports/`, including exact-path commands. They were never tracked and remain ignored; manual deletion is required. |

The in-app browser attach timed out. Playwright Chromium was used as the fallback. `docs/design/report-concept.png` and the latest rendered report were inspected via view_image at the same desktop dimensions. The fidelity ledger in `docs/design/README.md` records layout/color/control/source-detail comparisons and intentional dynamic-content differences. Final screenshots/PDF previews used for QA were kept outside the repository.

Real integration tests are separate because they invoke actual compilers and require network access on the first install. Reproduce:

```sh
python -m pytest --cov=sentinel.scanner --cov-report=term-missing
SENTINEL_RUN_INTEGRATION=1 python -m pytest tests/test_integration.py -q
python -m ruff check sentinel tests scripts app.py
python -m ruff format --check sentinel tests scripts app.py
python -m mypy
docker compose config --quiet
docker compose build
docker compose up -d --wait
```

PowerShell integration: set `$env:SENTINEL_RUN_INTEGRATION='1'`, run pytest, then remove that environment variable. Native Linux process-tree cleanup, Docker privileges/resource controls, Compose startup, and CI behavior remain unverified locally until Docker Desktop's Linux engine is running. Cross-platform type checking is not a substitute for those runtime checks.

SARIF schema reference: [OASIS SARIF schema](https://github.com/oasis-tcs/sarif-spec/blob/main/sarif-2.1/schema/sarif-schema-2.1.0.json). No claim of exhaustive vulnerability detection or exploit validation is made.
