# 02 — "/" always renders the landing page, even when signed in

**What to build:** The `/` route always shows the marketing landing page, regardless of whether the visitor has a valid session — a signed-in Candidate navigating to `/` (clicking the wordmark, a shared link, browser back, etc.) sees the landing page instead of being silently bounced to the Dashboard. The "Connect GitHub" CTA is hidden for a signed-in visitor (it's not a meaningful action for them), but nothing else about the page changes — no replacement CTA is added, since the existing global `AppHeader` already shows a Dashboard link when signed in.

**Blocked by:** 01 — OAuth success redirect goes straight to the Candidate Dashboard. Landing this ticket before 01 would strand a freshly-logged-in Candidate on the marketing page instead of their Dashboard, since today `Home`'s own redirect is the only thing that gets them there.

**Status:** ready-for-agent

- [ ] `Home`'s mount effect no longer redirects to `/dashboard` when `getMe()` resolves to a signed-in Candidate. It still calls `getMe()` to determine CTA visibility.
- [ ] The "Connect GitHub" CTA renders only when `getMe()` resolves to `null` (logged-out visitor). It stays hidden while the auth check is in flight and once it resolves to a signed-in Candidate (no CTA flash, no replacement CTA).
- [ ] No other part of `Home`'s markup becomes auth-conditional — heading, tagline, and all other landing content render identically regardless of sign-in state.
- [ ] `Home.test.tsx`'s "redirects a logged-in candidate to the dashboard" case is rewritten to assert the opposite: given `getMe()` resolves to a Candidate, `<Home>` renders landing page content and does not render "Connect GitHub" — no `/dashboard` route stub needed in the test anymore.
- [ ] `Home.test.tsx`'s "shows the connect button for a logged-out visitor" case is unchanged and still passes.
- [ ] `AppHeader`, `useRequireCandidate`, and every other authenticated page's redirect behavior are untouched.
