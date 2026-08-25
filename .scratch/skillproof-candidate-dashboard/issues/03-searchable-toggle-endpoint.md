# 03 — Searchable toggle endpoint

**What to build:** `searchable` can currently only be set as a field on a `/verify` call — there's no way to change it without re-running verification. Add a new authenticated endpoint that flips a Candidate's `searchable` flag on its own, using the same session-derived-identity pattern `/verify` already uses (ADR-0006), so a later client (the Candidate Dashboard) can let a Candidate opt in/out without a full re-verify.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A new authenticated endpoint updates the current Candidate's `searchable` flag, deriving identity from the session exactly as `/verify` does — never from a client-supplied `candidate_id`.
- [ ] Calling it without a valid session returns 401.
- [ ] Calling it persists the new value; a subsequent read of the Candidate reflects the change.
- [ ] `/verify`'s existing `searchable` field is unaffected and continues to work as it does today.
- [ ] Tested through the existing FastAPI `TestClient` seam (`tests/conftest.py`, the `_connect()` helper) — not a new testing pattern.
