# 04 — Provision Railway, Postgres, production OAuth App, and secrets

**What to build:** A real, running Railway project at `skillproof.up.railway.app` with a Postgres addon attached, a new production GitHub OAuth App registered with the matching callback URL, a `RAILWAY_TOKEN` GitHub repository secret, and every production environment variable set directly in Railway's dashboard.

**Blocked by:** 02 (needs the Dockerfile present in the repo to build against).

**Status:** done

- [x] A Railway project exists, claims the `skillproof` subdomain (`skillproof.up.railway.app`), and builds/deploys from this repo's Dockerfile.
- [x] A Postgres addon is attached in the same Railway project, injecting `DATABASE_URL` into the service's environment.
- [x] A new, separate GitHub OAuth App is registered for production, with callback URL `https://skillproof.up.railway.app/auth/github/callback` — the existing local-dev OAuth App and its `.env` config are left untouched.
- [x] A `RAILWAY_TOKEN` is generated and added as a GitHub repository secret, for ticket 03's deploy job to use.
- [x] Every production env var is set directly in Railway's dashboard: `SKILLPROOF_ENVIRONMENT=production`, the new OAuth App's `SKILLPROOF_GITHUB_CLIENT_ID`/`SKILLPROOF_GITHUB_CLIENT_SECRET`/`SKILLPROOF_GITHUB_OAUTH_REDIRECT_URI`, a freshly generated (not reused from any dev key) `SKILLPROOF_TOKEN_ENCRYPTION_KEY`, and the existing `SKILLPROOF_GROQ_API_KEY`. None of these are committed to the repo.

## Comments

Verified end to end: `https://skillproof.up.railway.app` builds and deploys from the Dockerfile (ticket 02), the Postgres addon injects `DATABASE_URL`, and a full GitHub OAuth login against the production app completes and lands on `/dashboard` signed in as the real GitHub user. One real bug surfaced and was fixed along the way: `SKILLPROOF_GITHUB_OAUTH_REDIRECT_URI` was initially set in Railway as `SKILLPROOF_GITHUB_OAUTH_REDIRECT_URL` (URL vs URI) — `config.py`'s field is `github_oauth_redirect_uri`, so the misnamed var never bound and the app silently fell back to its `localhost` default, which GitHub rejected as an unassociated redirect_uri. Renamed and redeployed; confirmed fixed by testing the live login flow.
