# 05 — Persistent navigation chrome

**What to build:** No page in the app currently has any navigation chrome — no header, no way back to `/` short of the browser's own back button. Add a small, viewer-agnostic header (present on every page) that provides a consistent way back, without ever becoming an owner-only affordance.

**Blocked by:** 02 (frontend test infrastructure)

**Status:** ready-for-agent

- [ ] A shared header component (at minimum, a wordmark linking to `/`) renders on every route in the app.
- [ ] The header's content and behavior do not vary based on session/auth state — a logged-in Candidate and a logged-out visitor see the identical header.
- [ ] The public Evidence Card page's existing session-blind invariant (identical output regardless of who's viewing) is unaffected — the header introduces no owner-only content or actions anywhere.
- [ ] Covered by a test asserting the header renders the same way for both a logged-in and a logged-out visitor.
