# Recruiter-facing screenshots and demo

Capture real scans, not fabricated output. Avoid confidential source/addresses. docs/design contains a generated reference, not product evidence.

## Screenshots

1. Open http://localhost:5000 in Chrome/Chromium. Set **1536x1024**, 100% zoom; hide bookmarks/developer overlays and use a fresh scan.
2. Upload `samples/OwnerControls.sol`. Expand mint/fee evidence with score, metadata, and filters visible. Save as `docs/images/report-desktop.png`.
3. Upload `samples/TxOrigin.sol`, show highlighted source/remediation, and optionally save `docs/images/tx-origin.png`.
4. Set **390x844** mobile dimensions. Expand the first finding and capture a full-page `docs/images/report-mobile.png`.
5. Create a temporary Broken.sol with `pragma solidity 0.8.30; contract Broken { function x( }`. Upload it, capture the unscored compile-error page as `docs/images/compile-error.png`, then delete that temporary file.
6. Replace the README image `docs/images/report-placeholder.svg` with `docs/images/report-desktop.png`. Add mobile/error images only if legible. Commit screenshots deliberately; generated scan reports stay ignored.

## Demo GIF (25-35 seconds)

- 0-5s: choose TxOrigin.sol and initiate a scan.
- 5-15s: show real loading/status. Preinstall the compiler so downloads do not dominate.
- 15-25s: expand the origin finding, show source/fix, filter High, search `origin`.
- 25-35s: export SARIF/PDF and show CLI `--fail-on high` exiting 1.

Record at 1280x800 or 1536x1024; optimize below roughly 8 MiB as `docs/images/demo.gif`. Insert `![Demo](docs/images/demo.gif)` below the README preview. If editing wait time, label the recording as edited.

## GitHub finishing checklist

- Push the logical commits and wait for CI; fix Linux/Docker differences before tagging v2.0.0.
- Finish Docker Desktop/WSL Linux-engine setup, run `docker compose build` and `docker compose up -d --wait`, then verify health and a real scan. This currently remains unverified locally.
- Remove the old local `venv/` and generated `reports/` folders manually. Automatic approval review blocked their deletion; both are ignored and untracked. Use the tested external venv instead.
- Repository description: **Solidity smart contract scanner with Slither, explainable scoring, SARIF exports, REST API, and a CI-ready CLI.**
- Topics: `solidity`, `smart-contract-security`, `web3`, `slither`, `static-analysis`, `python`, `flask`, `sarif`, `security-tools`.
- Enable GitHub private vulnerability reporting; SECURITY.md's link depends on that setting.
- Capture real screenshots/GIF, then release/tag after CI/Docker pass.
- Pin the repo on your profile. Prepare an interview walkthrough of failure invariants, compiler concurrency, false positives, canonical deduplication, scoring, and ZIP threat modeling.

No remote description/topics/releases/security settings/profile pins were changed.
