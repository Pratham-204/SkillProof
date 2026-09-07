# SkillProof — Production Deployment (Railway)

Status: ready-for-agent

## Problem Statement

SkillProof only runs locally — nobody but the developer can reach it. With a hackathon deadline days away, there's no live, publicly reachable instance to submit or demo. Ticket 09 (`skillproof-frontend` spec) already made the app's *configuration* correct for production (a required, persisted token-encryption key; an environment-driven `Secure` session cookie), but zero actual infrastructure exists: no host, no domain, no production GitHub OAuth App, and no deploy pipeline of any kind. The repo also has no Dockerfile, Procfile, or any other deploy config, and the built frontend (`frontend/dist`) is gitignored, so nothing today can turn this repo into a running, reachable service.

## Solution

Deploy SkillProof to Railway (starting on the free trial, upgradable to the $5/mo Hobby tier if needed) as a single Dockerized service, with a Railway-managed Postgres database for production only — local development keeps its existing SQLite default unchanged. The single-origin app (ADR-0006) is packaged via a multi-stage Dockerfile: a Node stage builds the gitignored `frontend/dist`, and a Python stage runs the existing FastAPI app, which already serves that build directly. GitHub Actions CI (previously added, then reverted) is re-added to run the full test suite on every push to `main`; on success, the workflow itself explicitly triggers the Railway deploy, rather than relying on Railway's native "Wait for CI" gate, which is currently unreliable. The app is reachable at `skillproof.up.railway.app`, authenticated through a dedicated new production GitHub OAuth App distinct from the existing local-dev one, and production starts from a completely empty database rather than carrying over local test/development data.

## User Stories

**Candidate & Recruiter — reaching a real product**

1. As a Candidate, I want to reach SkillProof at a real public URL, so that connecting my GitHub account and getting an Evidence Card isn't limited to whoever can run the project locally.
2. As a Recruiter, I want to search verified candidates from a public URL, so that using the product requires no local setup at all.
3. As a Candidate connecting via GitHub OAuth in production, I want that flow to use a dedicated production GitHub OAuth App (its own Client ID/Secret and callback URL), so that production authentication is never coupled to or broken by changes made to the local-dev OAuth App.
4. As a developer, I want the production OAuth App's callback URL to exactly match the deployed domain (`https://skillproof.up.railway.app/auth/github/callback`), matching the existing documented requirement in the README's deployment checklist.

**Developer — build and packaging**

5. As a developer, I want the app served as a single Docker image built via a multi-stage build, so the Node frontend build and the Python backend runtime are both captured in one portable, host-agnostic artifact.
6. As a developer, I want the frontend build (`frontend/dist`) to happen as part of the image build, so the gitignored build output never needs to be committed to the repository.
7. As a developer, I want the existing single-origin serving model (ADR-0006, `main.py`'s `FRONTEND_DIST` detection) to keep working unmodified inside the container, so this deployment work doesn't require touching how the app already serves its own frontend.

**Developer — database**

8. As a developer, I want production to use a managed Postgres database instead of a SQLite file, so candidate and evidence-card data survives redeploys/restarts on a platform whose filesystem isn't guaranteed persistent.
9. As a developer, I want local development to keep using SQLite exactly as it does today, so no new local infrastructure (e.g. a local Postgres instance) is required to keep developing the app day-to-day.
10. As a developer, I want the code that resolves the database connection URL to transparently handle Railway's injected `postgres://`-scheme URL, so the same `DATABASE_URL` Railway provides works without manual rewriting.
11. As a developer, I want production to start from a completely empty database, so my own local test/development data (test candidates, skills claimed while debugging) never appears in what becomes the public demo.

**Developer — CI/CD and deploy gating**

12. As a developer, I want every push to `main` to run the full test suite before anything reaches production, so a regression never reaches the live, publicly reachable instance.
13. As a developer, I want a passing test suite to trigger an automatic deploy, so shipping a fix doesn't require a manual deploy step.
14. As a developer, I want the deploy trigger enforced by the GitHub Actions workflow itself rather than Railway's native "Wait for CI" gate, so a currently-unreliable platform feature can't silently strand a deploy.
15. As a developer, I want a CI step that builds the Docker image, boots it, and checks a health endpoint responds, so a broken multi-stage build (a bad `COPY` path, a missing runtime dependency) is caught in CI rather than surfacing only as a failed Railway deployment.

**Developer — secrets and configuration**

16. As a developer, I want `SKILLPROOF_ENVIRONMENT=production` set in the deployed environment, so the existing production-mode safeguards (required token-encryption key, auto-secure session cookie) from ticket 09 actually engage.
17. As a developer, I want `SKILLPROOF_TOKEN_ENCRYPTION_KEY` to be a freshly generated, persisted Fernet key set directly in Railway's environment configuration, so stored GitHub tokens remain decryptable across restarts and redeploys.
18. As a developer, I want to reuse my existing `SKILLPROOF_GROQ_API_KEY` for production rather than provisioning a new one, so no new account/key management is introduced for a low-stakes, free-tier dependency.

**Developer — documentation and follow-through**

19. As a developer, I want this deployment's real architectural decisions (Docker over Railway's native buildpack, Postgres-in-production-only, Actions-triggers-deploy over Railway's native CI gate) recorded as ADRs, so a future reader understands why each was chosen over its real alternative.
20. As a developer, I want the README's deployment checklist updated to reflect the actual Railway-based process, so the existing "Deployment checklist (ticket 09)" section stops describing only bare environment variables and starts describing the real steps taken.
21. As a developer without direct access to Railway/GitHub account settings, I want a clear, explicit list of the account-level steps I still need to perform myself (creating the Railway project, registering the OAuth App, adding secrets, generating a Railway deploy token), so nothing required for a working deployment is silently assumed to already exist.
22. As a developer, I want local development to be completely unaffected by any of this (same SQLite default, same dev OAuth app, same `uvicorn --reload` workflow), so this deployment work introduces zero friction to the existing day-to-day dev loop.

## Implementation Decisions

- The app is packaged as a single multi-stage Docker image: an initial Node-based stage runs `npm install` and `npm run build` inside `frontend/`, producing `frontend/dist`; a subsequent Python-based stage installs the backend package and copies the built frontend output into the image, then runs the existing `uvicorn skillproof.main:app` entrypoint. This preserves ADR-0006's single-origin serving model with no code change to `main.py`'s existing `FRONTEND_DIST` detection logic.
- Railway is the hosting platform, using its GitHub-connected deploy model. Rather than relying on Railway's native "Wait for CI" deployment gate (reported unreliable at time of writing — deployments not triggering even after GitHub Actions passes), gating is enforced entirely within the GitHub Actions workflow itself: a test job runs first, and only on success does a subsequent job invoke Railway's CLI (authenticated via a `RAILWAY_TOKEN` repository secret) to trigger the deploy.
- Production uses Railway's managed Postgres addon, provisioned in the same Railway project, which injects a `DATABASE_URL` environment variable. The existing `database_url` setting and `make_engine()` already branch on URL scheme for SQLite-specific connection args; this is extended so a `postgres://`-scheme URL (Railway's format) is normalized to whatever scheme SQLAlchemy's chosen Postgres driver expects, without requiring a manually-rewritten URL.
- Local development is entirely unaffected: `database_url` keeps its existing `sqlite:///./skillproof.db` default — no local Postgres instance, Docker Compose, or other new local infrastructure is introduced by this work.
- Production starts from a schema-only, empty database — no data-migration path from the existing local `skillproof.db` is built, since that data is a local development/testing artifact, not real product data.
- A new, separate GitHub OAuth App is registered for production, with its callback URL set to `https://skillproof.up.railway.app/auth/github/callback`. The existing dev OAuth App (and its `.env`-configured `localhost` callback) is left completely untouched. Production's `SKILLPROOF_GITHUB_CLIENT_ID`/`SKILLPROOF_GITHUB_CLIENT_SECRET`/`SKILLPROOF_GITHUB_OAUTH_REDIRECT_URI` are set directly as Railway environment variables, never committed.
- `SKILLPROOF_ENVIRONMENT=production` is set in Railway, engaging the existing `_resolve_production_defaults` validator from ticket 09 (fail-fast on missing encryption key, auto-secure session cookie).
- `SKILLPROOF_TOKEN_ENCRYPTION_KEY` is a freshly generated Fernet key (generated once, not reused from any dev-generated key), set directly as a Railway environment variable, never committed or logged.
- `SKILLPROOF_GROQ_API_KEY` reuses the existing key already used for local development; no new Groq account/key is provisioned.
- The deployed subdomain is `skillproof.up.railway.app` (a Railway-provided platform subdomain); a custom purchased domain is explicitly deferred, not part of this work.
- Three decisions from this spec are significant enough to record as ADRs once implemented: choosing a Dockerfile over Railway's native Nixpacks buildpack, restricting Postgres to production only (local dev keeps SQLite), and enforcing the deploy gate via the GitHub Actions workflow itself rather than Railway's native "Wait for CI" feature.

## Testing Decisions

- A good test here verifies externally observable behavior — a resolved database connection string, or a container that actually boots and serves traffic — never internal implementation details of the Dockerfile or workflow YAML themselves.
- `tests/test_config.py` (the existing seam introduced in ticket 09 for `Settings`) is extended with tests covering the new Postgres `DATABASE_URL` scheme-normalization behavior: given a Railway-style `postgres://...` URL, `Settings`/`make_engine` resolves it to a working, correctly-scheme'd connection string, while the existing SQLite default path is completely unaffected. This follows ticket 09's own prior art exactly — its tests pin `token_encryption_key=""` explicitly to stay hermetic against whatever the developer's local `.env` happens to contain; the new Postgres tests follow the same hermetic-input pattern.
- One new seam is introduced: a CI smoke-test step that builds the Docker image, runs it, and curls a health check (`GET /`) against the running container before the build step is considered successful. This is the only seam capable of verifying the multi-stage build's actual correctness (frontend build succeeding, files landing where the backend expects them, the backend able to import and serve them) — no unit test can substitute for it, and it's the single new seam this spec introduces.
- The GitHub Actions workflow's own correctness (test-then-deploy job sequencing, the Railway CLI invocation) and the actual Railway deployment are not unit-testable; they're verified by direct execution once pushed, the same way ticket 09 treated its own startup fail-fast behavior as proven by direct execution rather than a synthetic test standing in for it.

## Out of Scope

- Purchasing and wiring a custom domain — explicitly deferred; the platform-provided `skillproof.up.railway.app` subdomain is the target for this pass.
- Migrating existing local `skillproof.db` data into production — production starts empty.
- Running Postgres locally for development parity — local dev keeps SQLite; this is a deliberately accepted, documented risk (SQLite/Postgres behavioral divergence), not solved here.
- Multi-instance/horizontal scaling of the deployed service — single Railway instance only; nothing here assumes or builds toward running more than one.
- Actually performing the account-level provisioning steps (creating the Railway project, registering the production GitHub OAuth App, generating and storing the `RAILWAY_TOKEN` and other secrets) — these require direct access to accounts this agent doesn't have, and are handed off as an explicit human-gated walkthrough rather than built here.
- Upgrading Railway's plan from the free trial to Hobby ($5/mo) — a payment action, left entirely to the user's discretion and timing.
- Sign-out/session termination, and any other previously-deferred authentication surface (see `CONTEXT.md` round 10) — unrelated to and unaffected by this deployment work.

## Further Notes

- This spec follows directly from a grilling session that resolved, with explicit user sign-off on each: hosting platform (Railway), database strategy (Postgres in production only), data handling (fresh production DB), build approach (Dockerfile over buildpack), and deploy gating (Actions-triggered over Railway's native CI wait).
- Ticket 09 (`skillproof-frontend` spec) already completed all of this deployment's *code-correctness* prerequisites — this spec is purely the infrastructure and deploy-pipeline work ticket 09 explicitly deferred as "lower priority... only matters once an actual deploy is imminent."
- The session-cookie `max_age` fix (30 days, landed just prior to this spec) becomes materially more relevant here — Railway restarts/redeploys are a routine, recurring event in a way a local dev server restart never was, and a Candidate's session needs to survive that.
- The hackathon submission deadline driving this work is approximately 9 days out from this spec's creation date.
