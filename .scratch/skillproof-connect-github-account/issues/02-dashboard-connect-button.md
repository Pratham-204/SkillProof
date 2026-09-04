# 02 — Merged "Connect GitHub Account" control on the Candidate Dashboard

**Status:** done

**What to build:** The Candidate Dashboard always shows a "Connect GitHub Account" button (an anchor to the existing `GITHUB_LOGIN_URL`, the same OAuth redirect used at first login) instead of only showing a reconnect link when `needs_reconnect` is true. Default copy explains the button covers both reconnecting a revoked token and switching to a different GitHub account, plus the caveat that GitHub has no forced account-picker — switching to a different account only works if the browser is already signed into that other GitHub account. When `needs_reconnect` is true, the same control shows urgent copy ("Your GitHub access was revoked...") merged into this one block, replacing today's separate amber banner rather than showing alongside it. `ClaimSkills.tsx`, `ScanReveal.tsx` (their existing conditional banners stay as-is), and `AppHeader.tsx` (stays session-blind) are not touched. No new frontend API calls or backend endpoints — this only changes what's rendered on the Dashboard.

**Blocked by:** None — can start immediately.

- [x] With `needs_reconnect: false`, the Dashboard renders a "Connect GitHub Account" button linking to `GITHUB_LOGIN_URL`, with copy explaining it covers reconnect + switching and the browser-account-picker caveat.
- [x] With `needs_reconnect: true`, the same button renders merged with urgent "access was revoked" copy in place of the old standalone amber banner — not alongside it.
- [x] `ClaimSkills.tsx` and `ScanReveal.tsx` keep their existing conditional `needs_reconnect` banners unchanged.
- [x] `AppHeader.tsx` is unchanged — still renders identically on every page regardless of session state.
- [x] `Dashboard.test.tsx`'s existing "shows a reconnect prompt when needs_reconnect is set" case is updated to assert the merged control; a new case covers the default (`needs_reconnect: false`) always-visible button and its copy.

## Comments

Implemented in `frontend/src/pages/Dashboard.tsx`: a single always-rendered block (styled via a locally-computed `connectAccountBannerClassName`, following the `lib/evidence.ts` className-variant precedent) replaces the old `needs_reconnect`-only banner, with a "Connect GitHub Account" link to `GITHUB_LOGIN_URL`, default copy covering reconnect + account-switching + the GitHub account-picker caveat, and urgent copy merged in when `needs_reconnect` is true. `ClaimSkills.tsx`, `ScanReveal.tsx`, and `AppHeader.tsx` are untouched — verified via `git status`. `Dashboard.test.tsx` updated: the old reconnect-prompt test replaced with two cases (default always-visible button + copy; merged urgent-copy state). Code review flagged that this diverges from `ScanReveal.tsx`'s still-separate banner — expected per this ticket's own scope, not fixed. tsc, oxlint, and the full frontend suite (22 tests) all pass.
