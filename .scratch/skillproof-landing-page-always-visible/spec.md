Status: ready-for-agent

## Problem Statement

`Home` (the `/` route) currently does double duty as both the marketing landing page and a post-login gate: on mount it calls `getMe()`, and if the session validates, it immediately redirects to the Candidate Dashboard. This means anyone with a valid `skillproof_session` cookie — including the builder iterating on the landing page, or a returning Candidate who deliberately navigates back to `/` — can never actually see the landing page. The only way to view it is to be logged out, or open an incognito tab, which defeats the point of having a landing page at all.

## Solution

`/` always renders the landing page, regardless of whether the visitor has a valid session. The post-login destination moves off of `/` entirely: a fresh GitHub OAuth login lands the Candidate directly on the Candidate Dashboard instead of bouncing through `/`. `Home`'s own "Connect GitHub" call-to-action is hidden for a signed-in visitor (since it's not a meaningful action for them), but nothing else about the page changes for them — the already-global `AppHeader` nav already exposes a Dashboard link when signed in, so `Home` doesn't need to duplicate that affordance.

## User Stories

1. As a logged-in Candidate, I want to be able to view the `/` landing page, so that I can see what a prospective Candidate or Recruiter actually sees before they sign up.
2. As a logged-in Candidate who navigates to `/` (e.g. by clicking a shared marketing link, or the wordmark), I want to land on the marketing page itself, so that I'm not silently redirected somewhere I didn't ask to go.
3. As a logged-in Candidate viewing `/`, I want the "Connect GitHub" button to not be shown to me, so that I'm not prompted to do something that's already done and makes no sense in my current state.
4. As a logged-in Candidate on `/`, I want a way to get to my Dashboard if I want to, so that the landing page doesn't strand me — this is already satisfied by the existing `AppHeader` Dashboard link and requires no new UI.
5. As a logged-out visitor, I want `/` to behave exactly as it does today (landing page with a "Connect GitHub" CTA), so that this change doesn't regress the existing first-time experience.
6. As a Candidate completing GitHub OAuth for the first time (or reconnecting), I want to land directly on my Candidate Dashboard, so that logging in still takes me straight to my own evidence instead of back through the marketing page.
7. As a developer debugging or demoing the product, I want to view the landing page while authenticated in my normal (non-incognito) browser session, so that I don't need a separate incognito workflow just to check landing page changes.
8. As a Candidate whose GitHub OAuth attempt fails (state mismatch or code-exchange failure), I want to end up somewhere sensible, so that a failed login doesn't strand me on a broken page — landing on the Candidate Dashboard's own auth guard, which bounces to `/`, is an acceptable (if slightly indirect) outcome for this pass.

## Implementation Decisions

- `Home` (`frontend/src/pages/Home.tsx`) no longer redirects on mount when `getMe()` resolves to a Candidate. The mount effect still calls `getMe()` to determine sign-in state (for the CTA visibility decision below), but the `navigate('/dashboard', { replace: true })` call is removed entirely.
- `Home`'s "Connect GitHub" CTA is rendered only when `getMe()` resolves to `null` (logged-out visitor) — it is hidden (not replaced with any other CTA) once the auth check resolves to a signed-in Candidate. While the auth check is in flight, the CTA stays hidden (existing `checking` behavior), avoiding a CTA flash for signed-in visitors.
- No other part of `Home`'s markup (heading, tagline, "[ SYSTEM ]" label, etc.) becomes auth-conditional — it renders identically for every visitor.
- The GitHub OAuth success redirect target (`Settings.github_oauth_success_redirect` in `src/skillproof/config.py`, currently defaulting to `"/"`) changes its default to `"/dashboard"`. This is the only backend change; `callback()`'s own branching logic is untouched.
- The two OAuth failure branches in `callback()` (state-mismatch, code-exchange failure) continue to redirect to the same `github_oauth_success_redirect` setting as today — they are not split out into a separate failure-redirect setting in this pass. A failed login will therefore redirect to `/dashboard`, which requires a session the failed attempt never established, so the existing Candidate Dashboard auth guard (`useRequireCandidate`) bounces the visitor back to `/` — landing them on the sign-in CTA, just via one extra redirect hop, with no error message shown. This is accepted as out of scope for this pass (see Out of Scope).
- `AppHeader` is unchanged — it already renders globally on every route and already shows a Dashboard link/chip conditional on sign-in state; this spec relies on that existing behavior rather than duplicating it in `Home`.
- `useRequireCandidate` (used by Dashboard, ClaimSkills, and other authenticated pages to redirect a signed-out visitor to `/`) is unchanged.

## Testing Decisions

Good tests here assert observable behavior (what renders, what the HTTP response redirects to) rather than internals (e.g. not asserting `checking` state directly, not asserting `navigate()` was or wasn't called).

- `frontend/src/pages/Home.test.tsx` (Vitest + Testing Library, existing seam — mocks `../api`'s `getMe`, renders `<Home>` inside a `MemoryRouter`):
  - The existing "redirects a logged-in candidate to the dashboard" case is rewritten to assert the opposite: given `getMe()` resolves to a Candidate, `<Home>` renders the landing page content and does **not** render the "Connect GitHub" text, and the test no longer needs a `/dashboard` route stub to redirect into.
  - The existing "shows the connect button for a logged-out visitor" case (given `getMe()` resolves to `null`) is unchanged.
  - A new case: while `getMe()` is pending (unresolved promise), neither "Connect GitHub" nor any landing-page-only auth state is shown — i.e. the CTA doesn't flash before the auth check resolves. (Optional, if not already implied by the existing `checking` gate.)
- `tests/test_api_flow.py` (pytest + FastAPI `TestClient`, existing seam — already drives `/auth/github/callback` with `follow_redirects=False` and asserts on the response):
  - Extend or add a case asserting that a successful `/auth/github/callback` response's `Location` header is `/dashboard`, not `/`.
  - No new test is added for the failure-branch redirect target change, since the failure branches' *destination setting* changes but their *test assertions* (if any currently assert a literal `"/"` Location) would need updating to `/dashboard` to stay accurate — check existing failure-path assertions in this file and update the expected Location value if they currently hard-code `/`.

## Out of Scope

- Splitting OAuth failure redirects into their own setting/destination distinct from the success redirect. Failures still land on `/dashboard` and bounce to `/` via the existing auth guard.
- Any change to `AppHeader`, `useRequireCandidate`, or any other authenticated page's redirect behavior.
- Sign-out/session-termination UI (already out of scope per CONTEXT.md round 10/11).
- Any new "Go to Dashboard" CTA inside `Home`'s own hero/body — the existing `AppHeader` Dashboard link is treated as sufficient.

## Further Notes

- This spec's scope was narrowed through grilling: the original complaint ("can't view the landing page unless logged out") turned out not to be an SEO issue (a logged-out visitor's experience is already unaffected by the reporter's own cookie) but a real UX gap for a builder iterating on the page and for a returning Candidate who deliberately navigates back to `/`.
- Investigation surfaced that `Home`'s redirect is currently the *only* mechanism sending a freshly-logged-in Candidate to the Dashboard (the OAuth callback itself redirects to `/` today, per `CONTEXT.md` round 10). Removing `Home`'s redirect without also repointing the OAuth success redirect would regress the post-login flow — hence the `config.py` change is included in this spec even though it wasn't part of the original complaint.
