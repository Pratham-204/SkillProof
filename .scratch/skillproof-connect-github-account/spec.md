# Connect GitHub Account: proactive reconnect + account switching

Status: ready-for-agent

## Problem Statement

A Candidate whose stored GitHub token has been revoked only finds out reactively — the amber "reconnect" banner only appears after a `/verify` run has already failed and flipped `needs_reconnect`. There's no way to reconnect proactively, before something breaks. Separately, a Candidate who wants to move to a *different* GitHub account entirely (verified against a personal account but wants a work account, or connected the wrong one by mistake) has no path to do that at all — the app has no sign-out and no account-switching affordance of any kind.

## Solution

One always-visible "Connect GitHub Account" button on the Candidate Dashboard fires the same `/auth/github/login` OAuth redirect already used at first login. Whichever GitHub identity authorizes on GitHub's side decides the outcome: the same account refreshes the stored token and clears `needs_reconnect`; a different account creates or resumes a separate Candidate and silently replaces the active session, with no merge between the two Candidates' Evidence Cards. There is no visible sign-out — switching accounts is implicit in authorizing as someone else. The existing conditional amber reconnect banner on the Dashboard is merged into this one control (urgent copy appears alongside the same button when `needs_reconnect` is true, rather than as a separate element); `ClaimSkills` and `ScanReveal` keep their own existing banners unchanged. The button's copy also explains that GitHub's OAuth flow has no forced account-picker, so switching only works if the browser is already signed into the other GitHub account. On the backend, `/auth/github/callback` is fixed to delete whatever session row the incoming request's cookie pointed at before issuing the new one, closing a pre-existing leak that left every prior login's session row orphaned.

## User Stories

**Candidate — reconnecting after a revoked token**

1. As a Candidate whose GitHub token has been revoked, I want a way to reconnect that doesn't require waiting for a failed verification to surface a banner, so I can fix my connection proactively.
2. As a Candidate with a currently valid connection, I want to see the same "Connect GitHub Account" button even when nothing is wrong, so reconnecting doesn't require deliberately breaking my token first.
3. As a Candidate whose token was just revoked, I want the Dashboard to explain why in the same place as the button, so I understand the button's urgency without hunting for a separate banner.
4. As a Candidate, I want reconnecting to be a single click through GitHub's OAuth flow (no separate form), matching how first login already works, so reconnecting isn't harder than logging in was.

**Candidate — switching to a different GitHub account**

5. As a Candidate who wants future verifications to pull from a different GitHub account, I want a way to authorize as that account, so my Evidence Cards can reflect a different identity going forward.
6. As a Candidate switching to a different GitHub account, I want that switch to create or resume a distinct Candidate profile with its own Evidence Cards, so my existing verified history under the old account isn't silently merged, mutated, or lost.
7. As a Candidate switching accounts, I want my browser session to move to the new Candidate automatically once GitHub authorizes, so I land on the new account's Dashboard without a separate manual step.
8. As a Candidate, I want no confirmation dialog or extra friction when switching accounts, so authorizing on GitHub is the only step required.
9. As a Candidate who clicks "Connect GitHub Account" while my browser is still signed into the same GitHub account, I want to be told upfront that I'll need to switch GitHub accounts in my browser first, so a silent no-op (landing back as myself) doesn't look like the app is broken.

**Candidate — the merged control**

10. As a Candidate, I want the button's copy to change depending on whether my token is currently revoked, so the same control is honest about being either "reconnect because it broke" or "connect / switch" when nothing is wrong.
11. As a returning Candidate on the ClaimSkills or ScanReveal pages with a revoked token, I want to keep seeing the existing amber reconnect banner there, so I'm not left without a next step just because the new button only lives on the Dashboard.
12. As a Candidate, I want the public, unauthenticated Evidence Card page and the app's global header to remain completely unaware of my session, so this feature doesn't leak an owner-only affordance onto a page anyone can view.

**Platform / system**

13. As the SkillProof system, I want a Candidate's stored GitHub token and `needs_reconnect` flag to update correctly whether the OAuth callback resolves to the same or a different `github_user_id`, so both reconnect and switch go through the exact same, already-tested code path.
14. As the SkillProof system, I want no new backend endpoint or schema for account-switching itself, so the existing `callback()` lookup-or-create-by-`github_user_id` logic stays the single source of truth for identity resolution.
15. As the SkillProof system, I want the previous session row deleted whenever a new one is issued at `/auth/github/callback`, so repeated logins, reconnects, and switches don't leave orphaned `CandidateSession` rows accumulating indefinitely.
16. As the SkillProof system, I want that session-row cleanup to apply uniformly regardless of whether the new login is a reconnect or a switch, so there's no special-cased branch that could diverge later.
17. As the SkillProof system, I want a first-time login (no existing session cookie) to be entirely unaffected by the cleanup logic, so first login isn't accidentally broken by code meant for reconnect/switch.

**Developer**

18. As a developer maintaining this codebase, I want the Dashboard's merged button/banner copy variants covered by a component test, so a future change to `needs_reconnect` handling doesn't silently drop the urgent-copy path.
19. As a developer maintaining this codebase, I want the session-row-cleanup behavior covered by a backend test through the existing `TestClient` seam, so the leak doesn't regress silently.
20. As a developer reading this code later, I want the "why one button, not two, and why no sign-out" reasoning already recorded rather than re-litigated here, so this spec can reference ADR-0014 and CONTEXT.md round 12 instead of restating the trade-off.

## Implementation Decisions

**Dashboard button/banner merge.** In `Dashboard.tsx`, the existing conditional amber block (rendered only when `needs_reconnect` is true) is replaced by a single, always-rendered block containing the "Connect GitHub Account" button (an anchor to `GITHUB_LOGIN_URL`, same target as today's "Reconnect GitHub" link). Default copy explains the button covers both reconnecting and switching, plus the GitHub account-picker caveat (the browser must already be signed into the target account for a switch to actually change identity). When `needs_reconnect` is true, urgent copy ("Your GitHub access was revoked...") is added to the same block rather than shown as a second, separate element — one control, one visual location, copy varies by state.

**No changes to `ClaimSkills.tsx` or `ScanReveal.tsx`.** Both keep their existing conditional `needs_reconnect` banners exactly as they are today, still linking to `GITHUB_LOGIN_URL`.

**No changes to `AppHeader.tsx`.** It stays session-blind, rendered identically on every page including `PublicEvidenceCard`; no new session-aware content is added there.

**No new frontend API surface.** The button reuses the existing `GITHUB_LOGIN_URL` constant from `api.ts`; no new fetch call, no new response fields.

**Backend session cleanup at `/auth/github/callback`.** The callback handler (`routers/auth.py`) gains access to the incoming `Request` to read the session cookie (`settings.session_cookie_name`) already present on the request, if any. If a cookie value is present, look up the matching `CandidateSession` row and delete it before committing the new session row — this runs identically whether the resolved `Candidate` is the same row as before (reconnect) or a different one (switch), and is a no-op when no cookie is present (first login). No schema changes; no new table or column.

**No changes to identity-resolution logic.** `callback()`'s existing lookup-or-create-by-`github_user_id` behavior is unchanged — it already does the right thing for account switching by construction; this spec only adds the cleanup step around it.

**No sign-out endpoint or UI.** Consistent with CONTEXT.md round 10 and round 12 — switching remains implicit in re-authorizing via GitHub, not a separate log-out action.

## Testing Decisions

A good test here asserts observable behavior — rendered copy, an anchor's `href`, a session cookie's effect on subsequent requests — never internal component state or ORM object identity.

**Backend** (seam: existing FastAPI `TestClient`, `tests/conftest.py` + `tests/test_api_flow.py`, using the existing `_connect()`-style helper):
- Reconnecting as the same `github_user_id` while holding a valid session cookie: the prior `CandidateSession` row is gone afterward, a new one exists, and `needs_reconnect` is cleared.
- Authorizing as a *different* `github_user_id` while holding an existing session cookie: the prior session row is deleted, a new (or resumed) `Candidate` is created/reused for the new identity, the new session cookie maps to that new Candidate, and the original Candidate's stored data (Evidence Cards, `github_login`, etc.) is untouched.
- First login with no session cookie present: callback succeeds exactly as it does today, with no error from the (skipped) cleanup step.

**Frontend** (seam: existing Vitest + React Testing Library, `Dashboard.test.tsx` pattern):
- With `needs_reconnect: false`, the "Connect GitHub Account" button renders, links to `GITHUB_LOGIN_URL`, and the account-picker explanatory copy is present.
- With `needs_reconnect: true`, the same button renders merged with the urgent copy in place of the old standalone amber banner (the existing `Dashboard.test.tsx` case "shows a reconnect prompt when needs_reconnect is set" is updated to assert the merged version rather than a separate block).
- No OAuth network flow is exercised in tests — `GITHUB_LOGIN_URL` is a static anchor target, same pattern as the existing reconnect link tests.

No Playwright or other end-to-end browser automation is introduced, consistent with the prior decision to keep frontend tests at the component/interaction level only.

## Out of Scope

- Visible sign-out / logout button or endpoint.
- A dedicated account-settings page — the button lives on the existing Dashboard only, not a new page or route.
- Broader session garbage collection or TTL-based expiry across all `CandidateSession` rows — only the one row displaced by the exact callback request that triggers is deleted.
- Merging or transferring Evidence Cards between two Candidates after a switch.
- Forcing GitHub to present an account picker — not possible via GitHub's OAuth API; the UI only explains the limitation, it doesn't work around it.
- Adding the new button to `ClaimSkills` or `ScanReveal` — those keep their existing banners unchanged.
- Any change to `AppHeader`'s session-blind behavior.

## Further Notes

This spec was produced through a grilling + domain-modeling session; the resolved decisions live in `CONTEXT.md` round 12 (new **Connect GitHub Account** glossary term) and `docs/adr/0014-one-connect-github-button-covers-reconnect-and-switch.md`, which records why this is one button rather than two, and why no visible sign-out was added.

The prior `skillproof-candidate-dashboard` spec introduced the Candidate Dashboard page and the original conditional reconnect banner this spec now merges into a single, always-visible control.
