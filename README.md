## Deployment

Production runs on [Vercel](https://vercel.com) as a single Python serverless function.

```
feature branch ──PR──▶ dev ──PR──▶ main ──▶ tests ──▶ vercel build/deploy ──▶ smoke test
                     (tests.yml)   │      (deploy.yml)
                                   └─ PRs into main get a preview deployment
```

- **CI** (`.github/workflows/tests.yml`) runs the test suite on every push/PR to `dev` and on PRs to `main`.
- **CD** (`.github/workflows/deploy.yml`) re-runs the tests, then builds and deploys with the Vercel CLI:
  pushes to `main` go to production, PRs into `main` get a preview URL. It then smoke-tests the deployment:
  `/health` must report the deployed commit, and `/`, `/stations`, `/route` and the favicon must work.
- Vercel's own Git auto-deploy is switched off in `vercel.json`, so untested code never ships.
- **Entrypoint**: `wsgi.py` (auto-detected by Vercel) exposes the Flask `app` from `src/big_o`.
  Gunicorn isn't used on Vercel; `gunicorn.conf.py` is only for running a production-style server elsewhere.
- `metro.db` is bundled with the function and opened read-only (Vercel's filesystem is read-only).
- Vercel needs Python 3.12+, which `.python-version` pins (CI tests on the same version).

### One-time setup

1. Create a `main` branch from `dev` and push it.
2. Install the CLI (`npm i -g vercel`), then in the repo run `vercel link` to create the Vercel project.
   This writes `.vercel/project.json` containing `orgId` and `projectId` (don't commit it).
3. Create a token at **vercel.com → Account Settings → Tokens**.
4. In GitHub: **Settings → Secrets and variables → Actions**, add
   - secrets `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`
   - variable `PRODUCTION_URL` = the production domain, e.g. `https://big-o.vercel.app` (no trailing slash)
   - optional secret `VERCEL_AUTOMATION_BYPASS_SECRET`, needed for preview smoke tests if Deployment
     Protection is on (Vercel → Project Settings → Deployment Protection → Protection Bypass for Automation)
5. Optionally add a branch protection rule on `main` requiring the **Tests** check to pass on PRs.

### Logging

- **Server**: every request is logged (method, path, status, duration, request ID); error
  responses include their error code, route searches log their result, and unexpected errors
  log a traceback. Each response carries an `X-Request-ID` header to match it to its log lines.
- **User interactions**: the page reports events (page loaded, route requested/found/failed,
  mode change, swap, stops added/removed, theme change, input rejected, JavaScript errors) to
  `POST /log`, which accepts only known event names with small flat details.
- **Where**: stdout always (Vercel → project → **Logs**). Locally also `.logs/big_o.log`
  (rotating, git-ignored); there's no log file on Vercel, whose filesystem is read-only.
- **Settings**: `LOG_LEVEL` (default `INFO`), `LOG_DIR` (default `.logs`; empty turns file logging off).

### Running the tests

```
uv run playwright install chromium   # once: browser for the UI tests in tests/e2e/
uv run pytest
```

`tests/e2e/` drives the real page in headless Chromium against a live server. Without the
browser installed those tests are skipped locally; in CI they're required.

### Running locally

```
uv run big-o                          # Flask dev server on http://127.0.0.1:5000
uv run gunicorn big_o.app:app         # production-style server on http://localhost:8000
```
