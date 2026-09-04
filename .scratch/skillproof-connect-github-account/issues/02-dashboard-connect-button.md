# 02 — Merged "Connect GitHub Account" control on the Candidate Dashboard

**What to build:** The Candidate Dashboard always shows a "Connect GitHub Account" button (an anchor to the existing `GITHUB_LOGIN_URL`, the same OAuth redirect used at first login) instead of only showing a reconnect link when `needs_reconnect` is true. Default copy explains the button covers both reconnecting a revoked token and switching to a different GitHub account, plus the caveat that GitHub has no forced account-picker — switching to a different account only works if the browser is already signed into that other GitHub account. When `needs_reconnect` is true, the same control shows urgent copy ("Your GitHub access was revoked...") merged into this one block, replacing today's separate amber banner rather than showing alongside it. `ClaimSkills.tsx`, `ScanReveal.tsx` (their existing conditional banners stay as-is), and `AppHeader.tsx` (stays session-blind) are not touched. No new frontend API calls or backend endpoints — this only changes what's rendered on the Dashboard.

**Blocked by:** None — can start immediately.

- [ ] With `needs_reconnect: false`, the Dashboard renders a "Connect GitHub Account" button linking to `GITHUB_LOGIN_URL`, with copy explaining it covers reconnect + switching and the browser-account-picker caveat.
- [ ] With `needs_reconnect: true`, the same button renders merged with urgent "access was revoked" copy in place of the old standalone amber banner — not alongside it.
- [ ] `ClaimSkills.tsx` and `ScanReveal.tsx` keep their existing conditional `needs_reconnect` banners unchanged.
- [ ] `AppHeader.tsx` is unchanged — still renders identically on every page regardless of session state.
- [ ] `Dashboard.test.tsx`'s existing "shows a reconnect prompt when needs_reconnect is set" case is updated to assert the merged control; a new case covers the default (`needs_reconnect: false`) always-visible button and its copy.
