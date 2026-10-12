# API and CLI

`POST /api/v1/scan` accepts multipart `contract` (or compatibility alias `file`). It returns HTTP 202 with `scan_id`, `state`, `status_url`, and `report_url`; `Location` is the polling URL. Poll `GET /api/v1/scan/<uuid>` every two seconds until state is terminal. States: queued, running, completed, compile_error, timeout, engine_error. Only completed scans have score/grade/risk; errors always use null. GET returns 404 for unknown/expired IDs. Queue exhaustion returns 503, invalid input 400, request size 413, rate limit 429.

```sh
curl -F contract=@samples/TxOrigin.sol http://localhost:5000/api/v1/scan
curl http://localhost:5000/api/v1/scan/REPLACE_WITH_RETURNED_UUID
```

The machine-readable OpenAPI 3.0.3 specification is at `/api/v1/openapi.json`. Source must be UTF-8 Solidity. The web form uses CSRF; the API is for credential-free multipart clients, with no CORS permission for other origins. UUIDs are bearer links, not authenticated access. Keep them private; default retention is 24 hours.

Exports: `/report/<uuid>/export/json`, `/sarif`, `/md`, `/pdf`. Exports are downloadable attachments; queued/running jobs return 409. Failed reports can be exported as explicitly unscored diagnostics. JSON carries the full normalized result; SARIF 2.1.0 includes source locations, rule help, fingerprints, and unsuccessful execution status for failures.

```sh
contract-radar scan samples/TxOrigin.sol --format json
contract-radar scan samples/TxOrigin.sol --format sarif --output contract_radar.sarif --fail-on high
contract-radar scan path/to/sources --format md
```

CLI exit codes: 0 completed below the selected threshold, 1 completed with findings at/above `--fail-on`, 2 input/engine/compilation/timeout failure. CLI never suppresses engine failures as success. File, ZIP, and source-directory input share validation; unrelated build scripts are not executed.

## Vercel request mode

On Vercel, `POST /api/v1/scan` returns HTTP 200 after analysis with a terminal state. Keep the upload request open. The response still contains report and status URLs; GET/report/export behavior is unchanged. Local background mode returns HTTP 202. Hosted admission/storage outages return 503, limits return 429, and failed scans never receive a score. See [DEPLOYMENT](DEPLOYMENT.md).
