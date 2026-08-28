# 02 — Dockerfile + CI build-and-boot smoke test

**What to build:** A multi-stage Dockerfile (a Node stage builds the gitignored `frontend/dist`; a Python stage runs the existing FastAPI app, which already serves that build via `main.py`'s single-origin `FRONTEND_DIST` logic, unchanged) that produces a working, bootable image. A new CI job builds the image, runs it, and curls a health check against it — the only seam that can verify the multi-stage build actually works end to end.

**Blocked by:** None — can start immediately (boots against the default SQLite; doesn't require ticket 01's Postgres support to exist).

**Status:** done

- [x] A multi-stage Dockerfile builds `frontend/dist` in a Node stage and runs the backend in a Python stage, with no changes needed to `main.py`'s existing frontend-serving logic.
- [x] The built image boots successfully with no environment variables set beyond defaults (i.e. against SQLite, matching local dev's default).
- [x] A new CI job builds the image, runs it, and asserts a health check (`GET /`) succeeds against the running container.
- [x] The CI job fails loudly (not silently) if the image fails to build or boot.
