# 01 — OAuth success redirect goes straight to the Candidate Dashboard

**What to build:** A Candidate who completes GitHub OAuth (fresh login or reconnect) lands directly on the Candidate Dashboard, instead of being routed through `/` first and redirected client-side from there. This is a pure backend redirect-target change: today `/auth/github/callback`'s success branch redirects to `/`, and it's `Home`'s own client-side auto-redirect that currently forwards a signed-in visitor on to `/dashboard`. This ticket makes the callback redirect to `/dashboard` directly, so the post-login flow no longer depends on `Home`'s redirect behavior — which ticket 02 is about to remove.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `Settings.github_oauth_success_redirect`'s default value changes from `"/"` to `"/dashboard"`.
- [ ] The two OAuth failure branches (state-mismatch, code-exchange failure) are left redirecting to the same `github_oauth_success_redirect` setting as today — no separate failure-redirect setting is introduced in this ticket.
- [ ] A successful `/auth/github/callback` request (existing `tests/test_api_flow.py` seam, `TestClient` with `follow_redirects=False`) asserts the response's `Location` header is `/dashboard`, not `/`.
- [ ] Any existing test in `tests/test_api_flow.py` that currently hard-codes an expected `Location` of `/` for the success path is updated to expect `/dashboard`. Failure-path assertions, if any exist, are checked and updated the same way since they share the same setting.
- [ ] Manual/local verification: completing GitHub OAuth end-to-end still results in landing on the Candidate Dashboard (as it does today, just via a direct redirect rather than a `Home`-mediated one).
