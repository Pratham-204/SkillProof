# SkillProof

Verifies a developer's self-reported skills against their public GitHub activity, producing a public Evidence Card per claimed skill instead of a self-reported resume line. See `.scratch/skillproof-mvp/spec.md` for the product spec and `CONTEXT.md` / `docs/adr/` for domain language and architecture decisions.

## Setup

```
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # macOS/Linux
```

Configure via environment variables (see `src/skillproof/config.py` for the full list and defaults), most importantly:

- `SKILLPROOF_GITHUB_CLIENT_ID` / `SKILLPROOF_GITHUB_CLIENT_SECRET` — a GitHub OAuth App's credentials.
- `SKILLPROOF_TOKEN_ENCRYPTION_KEY` — a Fernet key (`Fernet.generate_key()`); without one set, a fresh key is generated per process, which is fine for local dev but means stored tokens won't decrypt across restarts. **Required** (the app refuses to start without it) when `SKILLPROOF_ENVIRONMENT=production` — see the deployment checklist below.
- `SKILLPROOF_GROQ_API_KEY` — a Groq API key for the `/explain` endpoint (free tier). Explanations fall back to a deterministic template if unset or unavailable.

## Run

```
.venv/Scripts/uvicorn skillproof.main:app --reload
```

## Test

```
.venv/Scripts/pytest
```

Tests drive the full pipeline (connect → verify → poll → evidence card → explain → search) through the HTTP API, with GitHub and Groq faked and embeddings/scoring running for real — see `tests/conftest.py` and `tests/test_api_flow.py`.

## Frontend

The app is served single-origin (ADR-0006): FastAPI serves `frontend/dist/` directly once it's built, so there's no separate frontend server or CORS setup in production.

```
cd frontend
npm install
npm run dev     # Vite dev server on :5173 with HMR; proxies /auth, /verify, /evidence-card,
                 # /explain, /search, /skills to the FastAPI backend on :8000 — run that separately.
npm run build    # writes frontend/dist/, which FastAPI then serves for every non-API route.
```

## Taxonomy growth

The Skill Tag taxonomy self-extends (round 8 of `CONTEXT.md`, `docs/adr/0008-self-extending-taxonomy-skips-human-review.md`): `/verify` records a Sighting for any manifest-declared package matching no existing Skill Tag, and a separate batch job turns Sightings that clear a registry-existence check, a dedup check, and an LLM draft-or-abstain step into new, immediately claimable Skill Tags — no human approval step. Run it on a schedule (e.g. nightly cron) outside the app process:

```
.venv/Scripts/python -m skillproof.taxonomy_growth_cli
```

A running `uvicorn` process needs restarting to see any newly published Skill Tags — `skills.json` is read once and cached in-process, same as any other taxonomy edit.

## Deployment

SkillProof runs in production on [Railway](https://railway.app) as a single Dockerized service (`Dockerfile` — `docs/adr/0009-dockerfile-over-railways-native-buildpack.md`), with a Railway-managed Postgres addon (`docs/adr/0010-postgres-restricted-to-production-only.md`; local dev keeps the SQLite default above, unchanged). It's reachable at `https://skillproof.up.railway.app`.

**CI/CD**: every push to `main` runs `.github/workflows/ci.yml` — a `backend` job (mypy + pytest) and a `frontend` job (tsc + oxlint + vitest) run first, and only once both succeed does a `deploy` job invoke Railway's CLI (`railway up --service SkillProof`, authenticated via a `RAILWAY_TOKEN` repository secret) to trigger the production deploy. This gate lives in the workflow itself rather than Railway's native "Wait for CI" feature (`docs/adr/0011-actions-enforced-deploy-gate.md`); Railway's own auto-deploy-on-push is disabled for this service, so the Actions `deploy` job is the only path that can ship to production. A separate workflow, `.github/workflows/docker-smoke-test.yml`, builds and boots the image directly on every push/PR, catching a broken multi-stage build before it ever reaches Railway.

**Provisioning a new environment** (Railway project, Postgres addon, production GitHub OAuth App, secrets) is account-level work outside this repo's version control — see ticket 04's spec (`.scratch/skillproof-deployment/issues/04-provision-railway-oauth-secrets.md`) for the exact steps.

**Environment variables**, set directly in Railway's dashboard (never committed):

- **`SKILLPROOF_ENVIRONMENT=production`** — flips the two items below on automatically; the app refuses to start in this mode without a real encryption key (fails fast at import time, not on the first `/verify` call).
- **`SKILLPROOF_TOKEN_ENCRYPTION_KEY`** — must be an explicit, persisted Fernet key (`Fernet.generate_key()`), not left to the dev-only auto-generated-per-process default. That default regenerates on every restart/redeploy, which silently makes every previously-stored GitHub token undecryptable — every Candidate would need to reconnect. Generate once, store it (e.g. as a deploy secret), and never rotate it without expecting a mass reconnect.
- **Session cookie `Secure`** — defaults to `True` automatically once `SKILLPROOF_ENVIRONMENT=production` (no separate `SKILLPROOF_SESSION_COOKIE_SECURE` needed unless overriding). Do not deploy on production traffic that isn't HTTPS — a `Secure` cookie is silently dropped by browsers over plain `http://`, breaking login.
- **`SKILLPROOF_GITHUB_OAUTH_REDIRECT_URI`** — must exactly match the callback URL registered on the real deployed domain's **production** GitHub OAuth App (`https://<domain>/auth/github/callback`), byte-for-byte including scheme and trailing slash — this must be a separate OAuth App from the local-dev one, never the same Client ID/Secret. Note the field name ends in `_URI`, not `_URL`; a misnamed variable binds to nothing and silently falls back to the `localhost` default, breaking login with no error until someone tries it.
- **`DATABASE_URL`** — injected automatically by Railway's Postgres addon (bare, unprefixed — `Settings` accepts this alongside a `SKILLPROOF_DATABASE_URL` override, see ADR-0010). Nothing to set by hand beyond attaching the addon.
- **`SKILLPROOF_GROQ_API_KEY`** — reused as-is from local dev; no separate production key.
- **No CORS configuration needed** — confirmed no `CORSMiddleware` is present in `main.py`; the single-origin design (ADR-0006, frontend served by this same FastAPI app) means none should ever be added.