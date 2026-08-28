# 03 — GitHub Actions test-then-deploy workflow

**What to build:** GitHub Actions CI re-added (backend pytest+mypy, frontend vitest+tsc+lint — the workflow previously added in `274fdec` and reverted in `95001bc`) as a required job on push to `main`. A subsequent job, gated on that job passing, invokes Railway's CLI (authenticated via a `RAILWAY_TOKEN` repository secret) to trigger a deploy — enforcing the test-then-deploy gate within the workflow itself, not via Railway's native "Wait for CI" feature (reported unreliable).

**Blocked by:** 02 (Railway needs a Dockerfile in the repo to have anything to deploy).

**Status:** done

- [x] The full backend test suite (pytest+mypy) and frontend suite (vitest+tsc+lint) run on every push to `main` and on pull requests, as a required job.
- [x] A separate deploy job only runs after the test job succeeds — never in parallel, never on a failing test job.
- [x] The deploy job invokes Railway's CLI using a `RAILWAY_TOKEN` secret reference (the secret itself is provisioned in ticket 04 — this ticket's acceptance criteria don't require a live deploy to actually succeed, only that the workflow is correctly wired and the test job runs/passes).
- [x] No secrets are required for the test job itself to pass (matching the original CI's design — `SKILLPROOF_ENVIRONMENT` defaults to development, GitHub/Groq are faked in tests).
