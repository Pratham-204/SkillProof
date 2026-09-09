# 03 — Fix the redirect in the actual static landing page

**What to build:** Tickets 01 and 02 fixed `Home.tsx`, the React component mounted at `<Route path="/">` — but that route is unreachable for a real browser hit on `/`: `src/skillproof/main.py:99-103` registers a dedicated `@app.get("/")` route that always serves a separate, static, hand-authored file, `frontend/public/landing.html`, before the SPA catch-all ever runs. `landing.html` has its own independent copy of the exact redirect-on-signed-in logic ticket 02 removed from `Home.tsx` (a `<script>` tag that fetches `/auth/github/me` and calls `location.replace('/dashboard')` on success) — discovered only after 01 and 02 were deployed and the original bug was still reproducible live.

This ticket removes that redirect from `landing.html` and replaces it with the same "hide, don't redirect" treatment `Home.tsx` got — adapted for a static page with no `AppHeader`. `landing.html` has three separate "Connect GitHub" CTAs (nav, demo section, Hunter Card section) and no existing dashboard-navigation affordance of its own, so the nav CTA swaps to a "Dashboard" link for a signed-in visitor instead of just hiding (there needs to be *some* way back to the dashboard from this page), while the other two are hidden outright.

**Blocked by:** 01, 02 (both already implemented) — conceptually a correction to 02's actual deployed target, not new independent work.

**Status:** ready-for-agent

- [x] `landing.html`'s bottom `<script>` no longer calls `location.replace('/dashboard')` — `/` stays on the marketing page for every visitor, signed in or not.
- [x] The nav CTA (`id="nav-cta"`) swaps its `href` to `/dashboard` and its text to `Dashboard` when `/auth/github/me` resolves OK.
- [x] The other two CTAs (demo section, Hunter Card section — class `js-connect-cta`) are hidden (`hidden` attribute) when signed in, not replaced.
- [x] A logged-out visitor sees no change: all three CTAs visible, page unchanged.
- [x] Verified locally: built `frontend/dist` fresh, served it via a local uvicorn instance, confirmed via browser that (a) the logged-out path leaves all CTAs untouched and the page stays at `/`, and (b) mocking a signed-in `/auth/github/me` response swaps the nav CTA and hides the other two, with no navigation away from `/`.

## Comments

Root cause found by inspecting the live deployed JS bundle directly (content-hash matched a fresh local build, byte-inspected to confirm the `Home.tsx` redirect call was genuinely gone) and cross-checking Railway's deploy logs (build re-ran `npm run build`, container started fresh) — the deploy was correct, but `Home.tsx` was the wrong file. `main.py`'s own comment on `LANDING_PAGE` already documented that `landing.html` "runs its own `/auth/github/me` check and redirects... client-side" — this should have been caught during the original grilling/investigation phase before tickets 01/02 were scoped, not after deploy.
