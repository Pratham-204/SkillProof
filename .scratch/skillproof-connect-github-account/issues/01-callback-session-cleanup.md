# 01 — Clean up stale session row on GitHub OAuth callback

**Status:** done

**What to build:** `/auth/github/callback` should delete whatever `CandidateSession` row the incoming request's session cookie pointed to (if any) before creating and setting the new session row. This applies identically whether the callback resolves to the same Candidate (a plain reconnect after a revoked token) or a different Candidate (an account switch — GitHub authorized as a different `github_user_id`), and is a no-op when no session cookie is present (first login). No new endpoint, schema, or identity-resolution logic — `callback()`'s existing lookup-or-create-by-`github_user_id` behavior is unchanged; this only adds cleanup around it. This closes a pre-existing leak where every prior login/reconnect left its session row orphaned in the database forever.

**Blocked by:** None — can start immediately.

- [x] Reconnecting as the same `github_user_id` while holding a valid session cookie deletes the prior `CandidateSession` row, creates a new one, and clears `needs_reconnect`.
- [x] Authorizing as a *different* `github_user_id` while holding an existing session cookie deletes the prior session row, resolves/creates the new Candidate via the existing lookup-or-create logic, and issues a session cookie mapped to that new Candidate — the original Candidate's stored data (Evidence Cards, `github_login`, token) is untouched.
- [x] First login with no session cookie present succeeds exactly as it does today, with no error from the (skipped) cleanup step.
- [x] All three cases are covered by tests through the existing FastAPI `TestClient` seam (`tests/conftest.py` + `tests/test_api_flow.py`, using the existing `_connect()`-style helper) — no new test infrastructure.

## Comments

Implemented in `src/skillproof/routers/auth.py` (`callback()`) plus a new shared `get_session_by_cookie(request, db)` helper in `src/skillproof/deps.py`, reused by `get_current_candidate` — added during code review to remove a cookie→session lookup that would otherwise have been duplicated between the two call sites. Three new tests added to `tests/test_api_flow.py`: `test_reconnect_deletes_previous_session_row_and_clears_needs_reconnect`, `test_switching_github_account_replaces_session_without_merging_candidates`, `test_first_login_with_no_existing_session_cookie_succeeds`. Full suite (155 tests) and mypy pass.
