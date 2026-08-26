# 01 — Extract a shared "require Candidate" hook

**What to build:** `ClaimSkills` and `ScanReveal` each independently resolve the current Candidate via `getMe()` and redirect to `/` when logged out — the same logic duplicated twice already, about to become a third copy in the upcoming Candidate Dashboard. Extract it into one shared hook both existing pages adopt, so the identity-resolution pattern lives in exactly one place. Pure refactor — no behavior change.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] A single shared hook (or equivalent utility) resolves the current Candidate via `getMe()` and redirects to `/` when unauthenticated.
- [x] `ClaimSkills` and `ScanReveal` both use the shared hook in place of their own duplicated logic; their existing behavior (redirect-if-logged-out, loading state while resolving) is unchanged.
- [x] The hook's shape is generic enough that the Candidate Dashboard (a later ticket) can consume it directly rather than writing a third copy of the same pattern.
