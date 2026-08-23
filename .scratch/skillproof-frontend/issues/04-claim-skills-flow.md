# 04 — Claim-skills flow

**What to build:** The Candidate-facing screen where, after connecting GitHub, a Candidate selects skills to verify (autocomplete against `GET /skills`, capped at 8) and opts into `searchable`, then submits to kick off verification.

**Blocked by:** 01, 02.

**Status:** done

- [x] Home/connect route shows a GitHub connect button (`GET /auth/github/login`) when no session exists.
- [x] Once a session exists (post-callback redirect lands here), the claim-skills screen fetches `GET /skills` and offers autocomplete selection — free-text entry that doesn't match a real Skill Tag is not selectable, matching the backend's autocomplete-only claim model.
- [x] Selecting more than 8 skills is prevented client-side (matches the backend's fixed cap), with a clear indicator of the limit.
- [x] A `searchable` opt-in checkbox is shown alongside submission, defaulting unchecked.
- [x] Submitting calls `POST /verify` (no `candidate_id` in the payload post-ticket-01) with the selected skills and `searchable` value, then navigates to the live scan/reveal route.
- [x] If `needs_reconnect` is true on the current Candidate (stale/revoked token), the screen shows a reconnect prompt instead of (or alongside) the claim form.

## Comments

Implementation: `src/api.ts` is a small typed fetch layer (`getMe`, `listSkills`, `verify`, plus `getEvidenceCard`/`explainSkill`/`searchCandidates` added now since later tickets need them and the shape is settled) — all `credentials: 'same-origin'` so the session cookie rides along. `Home.tsx` calls `getMe()` on mount; a 401 shows the connect button (`<a href="/auth/github/login">`, a real navigation since it's an OAuth redirect, not a fetch), a live session redirects straight to `/claim`. `ClaimSkills.tsx` re-checks `getMe()` (redirecting home if unauthenticated), fetches `/skills`, and renders `components/SkillPicker.tsx` — an autocomplete-only multi-select (no free-text entry possible, matching CONTEXT.md's Skill Tag term) capped at `MAX_CLAIMED_SKILLS = 8`. `needs_reconnect: true` short-circuits to a reconnect prompt before the form renders at all. On submit, `verify(skills, searchable)` then `navigate('/scan', { state: { skills } })` — the selected list is handed to ticket 05 via router state so the live view can show placeholders before any reveal event arrives, without re-fetching anything.

**Testing gap, disclosed rather than glossed over:** Chrome browser tools aren't enabled in this session (would need `/chrome` or a restart), so this was verified via `tsc -b && vite build` (clean) and code review only — not an actual interactive run in a browser, and not a real GitHub OAuth round-trip (no GitHub OAuth App credentials configured in this dev environment). Both are worth doing for real before considering this ticket's UI trustworthy: (1) enable browser tools and click through Home → connect-button-target-URL → (after a real OAuth app is configured) ClaimSkills → skill picker interaction; (2) set up a real GitHub OAuth App for at least one true end-to-end login.

**Gap closed:** a real GitHub OAuth App was registered (`SkillProof (dev)`, callback `http://localhost:8000/auth/github/callback`) and its credentials wired into `.env`. Chrome browser tools were used to click through the full real flow: Home → "Connect GitHub" → real GitHub authorize screen → redirect back to `/claim` signed in as the real GitHub account → autocomplete search (typed "Python", "Docker", both resolved correctly with category hints) → chip selection updating the `N / 8 selected` counter and enabling "Verify N skills" → submit → real `POST /verify`. All worked as designed. One incidental finding: GitHub's OAuth consent screen ("Authorize <app>") didn't respond to synthetic/automated clicks (no navigation, no network request) after 3 attempts — had to have the human click it directly. Not a SkillProof bug, just a note for any future automated testing against a real GitHub OAuth consent screen.
