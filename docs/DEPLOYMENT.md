# Vercel deployment

Contract Radar can run on Vercel without Docker. `vercel_app.py` is a separate entrypoint; `python app.py`, the CLI, and Docker retain background scanning and SQLite.

## Hosted behavior

- Scans run inside the upload request, before the response is returned. The browser shows a scanning message; keep the page open. The API returns HTTP 200 with a terminal result. Local background mode continues to return HTTP 202 and a polling URL.
- The function has a 300-second platform limit; analysis has a 120-second deadline. No unmanaged background threads are used in hosted mode.
- Solidity 0.8.30, 0.8.20, and 0.7.6 are installed and verified by solc-select during the Linux build. Runtime compiler downloads are disabled. Other selected versions fail clearly and receive no score. The resolver selects the highest catalog version matching each pragma; exact pinned pragmas must match a bundled version.
- Source files live only in isolated `/tmp` directories and are removed before reports are saved. If the platform terminates an invocation abruptly, its ephemeral filesystem is reclaimed by the platform; no success response is promised.
- Normalized reports, including bounded snippets, are stored privately in Upstash Redis, with a 24-hour TTL. UUID report links remain bearer access: keep them private. Expiry does not remove provider backups.
- Shared Redis admission enforces ten submissions per minute per hashed client address and one active scan globally. Busy requests return 503 and delete prepared sources. A 260-second owner-checked lease recovers after interrupted requests. This is a portfolio deployment with bounded throughput, not a distributed queue.
- Static assets are copied to `public/static` for Vercel CDN serving. SVG/favicon URLs match local mode.

## Setup

1. Create/link a Flask project in your intended Vercel workspace.
2. Connect a free Upstash for Redis marketplace resource in the same region (iad1). Disable automatic plan upgrades. Vercel provisions `KV_REST_API_URL` and `KV_REST_API_TOKEN`; `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` are also supported.
3. Set a randomly generated `SECRET_KEY` of at least 32 characters in production and preview. Never commit or publish it.
4. Deploy using the checked-in `vercel.json` and Python 3.12 configuration. The build script packages verified native Linux compilers and static assets.
5. Verify health, upload a safe and vulnerable contract, submit invalid Solidity, download all exports, and confirm report retrieval across separate requests before assigning the production domain.

To deploy from GitHub automatically, connect your GitHub login in Vercel account settings and authorize repository access, then link `ShkS44D/Contract-Radar` with production branch `main`. CLI deployments also work without that connection.

Secrets, pulled environment files, platform linkage, local compiler caches, and local agent integrations are ignored. Vercel and database free-tier quotas still apply; upgrades are not automatic. Monitor usage and protect admission further before broad public exposure.
