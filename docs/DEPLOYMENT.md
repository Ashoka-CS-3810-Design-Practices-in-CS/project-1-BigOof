# Deployment

Production runs on [Vercel](https://vercel.com) as a single Python serverless function, at
https://project-1-big-oof.vercel.app.

## Pipeline

```
feature branch ──PR──▶ dev ──PR──▶ main ──▶ tests ──▶ vercel build/deploy ──▶ smoke test
                     (tests.yml)   │      (deploy.yml)
                                   └─ PRs into main get a preview deployment
```

- **CI** (`.github/workflows/tests.yml`) runs the test suite on every push or PR to `dev`, and
  on PRs to `main`.
- **CD** (`.github/workflows/deploy.yml`) re-runs the tests, then builds and deploys with the
  Vercel CLI. Pushes to `main` go to production; PRs into `main` get a preview URL.
- **Smoke test**: after deploying, the workflow checks that `/health` reports the deployed
  commit, and that `/`, `/stations`, `/route` and the favicon all work.
- **No untested deploys**: Vercel's own Git auto-deploy is switched off in `vercel.json`, so
  only this workflow deploys.

## How the app runs on Vercel

- **Entry point**: `wsgi.py`, which Vercel detects automatically, exposes the Flask `app`
  from `src/big_o`. Gunicorn isn't used on Vercel; `gunicorn.conf.py` is only for running a
  production-style server elsewhere.
- **Database**: `metro.db` is bundled with the function and opened read-only, because
  Vercel's filesystem is read-only.
- **Python**: Vercel needs 3.12 or newer. `.python-version` pins 3.12, and CI tests on the
  same version.
- **Bundle**: only runtime dependencies (Flask, Gunicorn) are packaged. `vercel.json`
  excludes tests, docs and migrations.

## One-time setup

1. Install the Vercel CLI. It needs Node 20+; [nvm](https://github.com/nvm-sh/nvm) is the
   easiest way to get that without `sudo`:
   ```
   nvm install 22
   npm i -g vercel
   ```
2. In the repo, run `vercel login`, then `vercel link` to create or link the Vercel project.
   This writes `.vercel/project.json` (git-ignored), which contains `orgId` and `projectId`.
3. Create a token at **vercel.com → Account Settings → Tokens**.
4. In GitHub, open **Settings → Secrets and variables → Actions**.
   - On the **Secrets** tab, add `VERCEL_TOKEN`, `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID`.
   - On the **Variables** tab, add `PRODUCTION_URL` = `https://project-1-big-oof.vercel.app`,
     with no trailing slash.
   - For preview smoke tests, also add the secret `VERCEL_AUTOMATION_BYPASS_SECRET`. Get its
     value from Vercel → Project Settings → Deployment Protection → Protection Bypass for
     Automation.
5. Recommended: add a branch protection rule on `main` that requires a pull request and a
   passing **Test** check.

To deploy by hand, outside the pipeline, run `vercel --prod` from the repo.

## Troubleshooting

| Symptom in the Deploy workflow | Cause and fix |
|---|---|
| `VERCEL_TOKEN secret is not set` | Add the secrets from step 4. |
| `uv is required but was not found in PATH` | `vercel build` needs uv on the runner. The workflow installs it; keep the *Install uv* step. |
| `behind Vercel Deployment Protection (HTTP 302)` | Previews are login-protected. Add or fix the `VERCEL_AUTOMATION_BYPASS_SECRET` **Actions secret** (not a variable). The log says whether the secret was provided. |
| `serving commit '…', expected …` | The site isn't running the commit just deployed. Re-run the workflow; if it repeats, check the Vercel dashboard for a failed or pending deployment. |

## Logging

- **Server**: every request is logged with method, path, status, duration and a request ID,
  which is also returned in the `X-Request-ID` header. Error responses include their error
  code, route searches log their result, and unexpected errors log a traceback.
- **User interactions**: the page reports events to `POST /log`. These are page loaded, route
  requested, found or failed, mode change, swap, stops added or removed, theme change, input
  rejected, and JavaScript errors. The endpoint only accepts known event names with small,
  flat details.
- **Where**: always stdout, which on Vercel appears under **Project → Logs**. Locally, logs are
  also written to `.logs/big_o.log` (rotating and git-ignored). There's no log file on Vercel,
  whose filesystem is read-only.
- **Settings**: `LOG_LEVEL` (default `INFO`) and `LOG_DIR` (default `.logs`; set it to an
  empty string to turn file logging off).
