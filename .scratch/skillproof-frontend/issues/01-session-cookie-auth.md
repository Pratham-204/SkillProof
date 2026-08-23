# 01 — Session-cookie auth replaces client-supplied candidate_id

**What to build:** `GET /auth/github/callback` sets an HttpOnly session cookie and redirects into the frontend instead of returning `CandidateOut` as JSON. `POST /verify` and the `searchable` toggle derive `candidate_id` from that session instead of trusting the request body. Closes the pre-existing gap where a publicly-known `candidate_id` was sufficient to act as that Candidate.

**Blocked by:** none.

**Status:** done

- [x] A session store exists (a `Session` table or signed-cookie approach — implementer's call) mapping an opaque session id to `candidate_id`.
- [x] `GET /auth/github/callback` creates/refreshes the Candidate as it does today, then sets an HttpOnly session cookie and issues a redirect (not a JSON response) to a frontend route.
- [x] Session cookie is `Secure` outside local dev (env-driven, matching the existing `Settings` pattern in `config.py`).
- [x] `POST /verify` no longer accepts `candidate_id` in `VerifyRequest` — it's read from the session. Requests with no valid session are rejected (401).
- [x] The `searchable` toggle (currently part of the `/verify` payload) is likewise session-derived, not client-supplied.
- [x] A request with a missing, expired, or tampered session cookie gets a clear 401, not a 500 or a silent no-op.
- [x] Existing tests in `tests/test_api_flow.py` are updated to drive the new session-based flow (capture the cookie from the callback response, send it on subsequent requests) rather than passing `candidate_id` directly.

## Comments

See ADR-0006 for the rationale and CONTEXT.md round 7 for the resolved Candidate-authentication decision this implements.

Implementation: a `CandidateSession` table (`models.py`) maps an opaque `secrets.token_urlsafe(32)` session id to `candidate_id`; `deps.get_current_candidate` resolves the cookie to a `Candidate` or raises 401. `GET /auth/github/callback` now redirects (`Settings.github_oauth_success_redirect`, default `/`) and sets the cookie instead of returning JSON. A new `GET /auth/github/me` was added beyond the original checklist — it's the endpoint a frontend (and this ticket's own tests) need to resolve "who am I" from the cookie alone, since candidate_id is no longer handed back at callback time. `POST /verify` takes `candidate` via `Depends(get_current_candidate)`; `VerifyRequest` no longer has a `candidate_id` field. `tests/test_api_flow.py`'s `_connect` helper now follows the callback with `follow_redirects=False`, then calls `/auth/github/me` to get the identity dict tests previously read straight off the callback response. All 75 existing tests pass unchanged in behavior; `mypy` clean.
