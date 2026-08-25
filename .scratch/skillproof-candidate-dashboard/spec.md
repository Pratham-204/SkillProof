# Candidate Dashboard & Navigation Fixes

Status: ready-for-agent

## Problem Statement

A returning Candidate who logs back in has no way to see what they've already proven. `Home` immediately redirects a logged-in Candidate straight into `/claim` (claim more skills) even though the backend already has everything needed to show their existing Evidence Cards — there's just no page that displays it. Separately, the frontend has no persistent navigation of any kind (no header, no "back to home" link on any page), and the one place that does rely on browser navigation state (`ScanReveal`, which reads its expected skill list from React Router's `location.state`) silently breaks when a Candidate uses the browser's own back button, refreshes, or lands on the page any way other than the one exact in-app path it assumes — exactly the "no back button" complaint.

## Solution

A new Candidate Dashboard becomes the authenticated landing experience: `Home`'s post-login redirect target moves from `/claim` to this new page, which shows the Candidate's own Evidence Cards (the same latest-per-skill set every other Evidence Card view already returns), a copyable link to their public Evidence Card, and a `searchable` toggle they can flip without re-running verification. A small, viewer-agnostic navigation header is added across every page so there's always a consistent way back to `/`. `ScanReveal`'s completion detection is changed to derive its expected skill set from the Candidate's own in-progress Evidence Cards (queried from the backend) instead of trusting `location.state`, so it behaves correctly regardless of how the page was reached. A recruiter-facing portal (accounts/login) is explicitly not part of this work — it would reverse an existing, recorded product decision and is deferred to its own future design session.

## User Stories

**Candidate — the dashboard**

1. As a Candidate, I want to land on a dashboard showing my previously verified skills when I log back in, so I don't have to re-verify or dig through a claim form just to see what I already proved.
2. As a Candidate, I want the dashboard to show the same Confidence Score, evidence type, and explanation I'd see on my public Evidence Card, so there's no discrepancy between what I see and what a Recruiter sees.
3. As a Candidate, I want to see only the current (latest) version of each skill's card on my dashboard, not older forked versions from before a taxonomy update, so the view stays as simple as every other Evidence Card view in the product.
4. As a Candidate, I want a "claim more skills" action from my dashboard, so adding new skills later doesn't require navigating away from my own data first.
5. As a Candidate with a revoked GitHub token, I want the dashboard to tell me I need to reconnect, so I understand why my data might be stale before I try to claim more skills.

**Candidate — sharing and searchability**

6. As a Candidate, I want to see and copy my own public Evidence Card link from the dashboard, so I can hand it to a recruiter without having to construct the URL myself.
7. As a Candidate, I want to toggle whether I'm searchable directly from the dashboard, so opting in or out doesn't require re-running verification just to change one setting.
8. As a Candidate, I want the searchable toggle to take effect immediately and reflect back to me, so I always know whether I'm currently discoverable in search.

**Candidate / visitor — navigation**

9. As a Candidate, I want a consistent way to get back to my dashboard or the home page from any page in the app, so I'm never stuck relying only on the browser's own back button.
10. As a first-time visitor, I want the same lightweight navigation chrome a logged-in Candidate sees, so the app feels consistent whether or not I'm signed in.
11. As a Recruiter or stranger viewing a public Evidence Card, I want the page to look and behave exactly as it would for anyone else, so nothing about the navigation chrome implies I'm the card's owner or have special access.

**Candidate — verification resilience**

12. As a Candidate mid-verification, I want to navigate away from the scan/reveal page and come back without losing track of which skills are still processing, so using the back button doesn't corrupt or lose my in-progress run.
13. As a Candidate mid-verification, I want the reveal page to determine completion from the actual state of my Evidence Cards, not from data that only exists if I arrived via one specific in-app link, so refreshing the page never leaves the UI stuck or showing the wrong thing.
14. As a Candidate who lands directly on the scan/reveal URL without having just submitted a claim (e.g. via back/forward navigation), I want the page to still behave correctly using only my identity, so the flow doesn't depend on fragile browser navigation state.

**Platform / system**

15. As the SkillProof system, I want a Candidate's `searchable` flag to only be changeable by that authenticated Candidate, so the new toggle endpoint doesn't reopen the trust gap ADR-0006 already closed for `/verify`.
16. As the SkillProof system, I want the dashboard to reuse the existing `/evidence-card/{candidate_id}` and `/auth/github/me` endpoints rather than introduce a parallel data path, so the Candidate's own view and the public view can never silently diverge.
17. As a developer maintaining this codebase, I want the new Dashboard component and the ScanReveal completion logic to have automated component tests, so future changes to either don't silently regress the way the current `location.state` dependency already has.
18. As a developer maintaining this codebase, I want the new backend endpoint to go through the same FastAPI test-client seam as the rest of the suite, so it doesn't introduce a second, inconsistent way of testing authenticated writes.

## Implementation Decisions

**New endpoint for `searchable`.** A new authenticated endpoint (e.g. `PATCH /candidates/me/searchable`, body `{"searchable": bool}`) using the existing `get_current_candidate` dependency — the same session-derived-identity pattern `/verify` already uses (ADR-0006). No schema change: it writes the existing `Candidate.searchable` column. `POST /verify`'s existing `searchable` field on `VerifyRequest` is unchanged and continues to work alongside this.

**Candidate Dashboard page.** A new frontend route (`/dashboard`) that, on mount, calls the existing `getMe()` and `getEvidenceCard(candidateId)` and renders the existing `EvidenceCardList` component against the result — no new backend read endpoint. Adds: the Candidate's `github_login`, a copy-to-clipboard control for their public Evidence Card link (`/c/{candidateId}`), a searchable toggle wired to the new endpoint above, a "claim more skills" link to `/claim`, and the existing `needs_reconnect` banner treatment already used in `ScanReveal`.

**`Home` redirect target.** `Home.tsx`'s post-login redirect changes from `navigate('/claim', { replace: true })` to `navigate('/dashboard', { replace: true })`. Unauthenticated behavior (landing copy + Connect GitHub button) is unchanged.

**Navigation chrome.** A new shared header component, rendered via a layout wrapper around every route in `App.tsx`. It contains only a wordmark linking to `/` — no session-aware content and no owner-only affordances of any kind, so it renders identically for every viewer on every page. This is deliberate: `PublicEvidenceCard.tsx` has a documented invariant that it's session-blind (a Candidate viewing their own public link sees exactly what a stranger sees), and the header must not become the thing that quietly breaks that.

**`ScanReveal` completion fix.** Drop the `location.state`-derived `claimedSkills` array entirely. On mount (alongside the existing `getMe()` call), fetch the Candidate's own Evidence Cards and derive the expected-completion set from whichever are `status === "processing"` at that point, rather than from router state passed only by one specific navigation path. The existing SSE-driven `scan`/`reveal`/`done` event handling is unaffected — only the "are we done yet" check changes its data source.

**Frontend test seam (new).** Vitest + `@testing-library/react` (+ `@testing-library/jest-dom`, `@testing-library/user-event`) added as devDependencies, configured against the existing Vite setup. This is the first automated frontend test infrastructure in the repo.

**Explicitly not built in this pass:** a recruiter-facing portal (accounts, login, saved candidates — see Out of Scope), a sign-out/logout endpoint, and any Evidence Card version-history browsing UI.

## Testing Decisions

**Backend.** Same seam as the existing suite (`tests/conftest.py`, `tests/test_api_flow.py`): drive the new endpoint through the FastAPI `TestClient`, establishing a session via the existing `_connect()` helper, faking only GitHub/Groq. New coverage: toggling `searchable` persists and is reflected in a subsequent read; calling the endpoint without a session cookie returns 401, mirroring how `/verify`'s auth requirement is already covered.

**Frontend (new).** Component/interaction-level tests via Vitest + React Testing Library. A good test here asserts observable behavior — what renders, what a user can see and click, and what changes as a result — never internal component state or prop shapes. Specifically: the Dashboard renders cards from a mocked `getEvidenceCard`/`getMe`, and the searchable toggle calls the new endpoint and reflects the resulting state; `Home` redirects an already-logged-in Candidate to `/dashboard`; `ScanReveal` computes its completion condition from processing-status cards rather than `location.state`, including the case where `location.state` is entirely absent (simulating a direct visit or back/forward navigation). No end-to-end/browser automation (e.g. Playwright) is introduced — animation/reveal feel remains a manual `/run`-style check, as it already was for the original scan/reveal work.

## Out of Scope

- **A recruiter-facing portal** (accounts, login, saved candidates, messaging) — this would reverse the existing, recorded "no Recruiter account" decision (see the Recruiter term and Notes in `CONTEXT.md`). Deferred to its own future grilling session, likely with an ADR given it reverses a written decision.
- **Sign-out / session termination** — no logout endpoint or UI is added; ending a session is unaffected by this spec.
- **Evidence Card version history** — the dashboard shows only the latest `taxonomy_version` per skill, matching every existing Evidence Card view; browsing older forked versions is not built.
- **Frontend performance optimization** (bundle size, load time) — "optimizing the frontend" in this spec means navigation/back-button correctness only.
- **End-to-end/browser test automation** — the new frontend test seam is component/interaction-level (Vitest + React Testing Library) only; no Playwright or similar.

## Further Notes

This spec was produced through a grilling + domain-modeling session; the resolved decisions live in `CONTEXT.md` round 10, including the new **Candidate Dashboard** glossary term.

The earlier `skillproof-frontend` spec (`.scratch/skillproof-frontend/spec.md`) already called for "component/interaction-level (React Testing Library)" frontend tests, but that tooling was never actually installed — `frontend/package.json` has no test dependencies and no `*.test.tsx` file exists anywhere in the repo today. This spec is what actually introduces that infrastructure for the first time; it should be set up once, generally, rather than narrowly scoped to only the components this spec touches.
