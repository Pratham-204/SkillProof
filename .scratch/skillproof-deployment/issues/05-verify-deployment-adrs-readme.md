# 05 — Verify live deployment end-to-end; write ADRs; update README

**What to build:** Proof that the whole pipeline actually works — push to `main` flows through tests passing, a deploy firing, `skillproof.up.railway.app` serving the real app, GitHub OAuth round-tripping against the new production app, and data persisting in Postgres across a redeploy. Once proven, the three ADRs this spec calls for are written, and the README's deployment checklist is updated to describe the real process instead of only bare environment variables.

**Blocked by:** 03, 04.

**Status:** done

- [x] A push to `main` is confirmed to run tests, then deploy, then result in `skillproof.up.railway.app` serving the current build. (CI run #5, commit e13defa: `backend`+`frontend`+`deploy` all green, `railway up --service SkillProof` succeeded.)
- [x] GitHub OAuth login against the live URL is confirmed to work end-to-end (new production OAuth App, correct callback), producing a real Candidate session. (Verified together with the user in-browser; also caught and fixed a `SKILLPROOF_GITHUB_OAUTH_REDIRECT_URI`/`_URL` naming bug along the way.)
- [x] Data written during that session is confirmed to still be present after a redeploy (proving Postgres persistence, not an ephemeral filesystem). (Candidate `fdcbabaf-c315-4d75-a074-c968fdc533c4` created, then a Railway manual redeploy triggered, then confirmed still present via `GET /evidence-card/{id}` — this also surfaced and fixed a real bug: `Settings.database_url` never bound Railway's bare `DATABASE_URL`, so production had silently been running on ephemeral per-container SQLite the whole time; see ADR-0010.)
- [x] Three ADRs are written: `docs/adr/0009-dockerfile-over-railways-native-buildpack.md`, `docs/adr/0010-postgres-restricted-to-production-only.md`, `docs/adr/0011-actions-enforced-deploy-gate.md`.
- [x] `README.md`'s "Deployment checklist" section is replaced with a "Deployment" section describing the actual Railway-based process (Dockerfile, Postgres addon, production OAuth App, `RAILWAY_TOKEN`-gated Actions deploy) rather than only bare environment variables.

## Comments

Two real bugs were found and fixed only because this ticket's verification was done against the actual live deployment rather than assumed from the design: the `DATABASE_URL`/`SKILLPROOF_DATABASE_URL` prefix mismatch (ADR-0010) and the `_URI`/`_URL` OAuth redirect variable typo. A third issue was found and fixed in `ci.yml` itself: `railway up` alone failed with "Multiple services found" once Postgres was attached — needed `--service SkillProof`. ADR-0011's originally-documented gap (Railway's native auto-deploy-on-push left enabled alongside the Actions-enforced gate) has since been closed: auto-deploy is now disabled for this service, so `ci.yml`'s `deploy` job is the only path that can trigger a production deploy.
