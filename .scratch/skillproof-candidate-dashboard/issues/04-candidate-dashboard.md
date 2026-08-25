# 04 — Candidate Dashboard

**What to build:** A logged-in Candidate currently has no way to see what they've already had verified — logging back in drops them straight into the claim form. Add a Dashboard page that becomes the authenticated landing experience: it shows the Candidate's existing Evidence Cards, a shareable link to their public card, a `searchable` toggle, and a way to claim more skills.

**Blocked by:** 01 (shared Candidate hook), 02 (frontend test infrastructure), 03 (searchable toggle endpoint)

**Status:** ready-for-agent

- [ ] A logged-in Candidate visiting the dashboard sees every skill they've had scored, using the same latest-`taxonomy_version`-per-skill data `/evidence-card/{candidate_id}` already returns — no new backend read endpoint.
- [ ] The dashboard shows a copyable link to the Candidate's own public Evidence Card.
- [ ] The dashboard includes a `searchable` toggle wired to the endpoint from ticket 03; toggling it updates immediately and reflects the persisted value.
- [ ] The dashboard offers a "claim more skills" action leading to the existing claim flow.
- [ ] A Candidate with `needs_reconnect` set sees the existing reconnect-prompt treatment (as already shown elsewhere in the app).
- [ ] `Home`'s post-login redirect target changes from the claim flow to this dashboard; `Home`'s unauthenticated behavior (landing copy, Connect GitHub) is unchanged.
- [ ] The dashboard resolves the current Candidate via the shared hook from ticket 01, not a new duplicate of that logic.
- [ ] Covered by component/interaction tests (using ticket 02's seam) asserting: cards render from the Candidate's data, the searchable toggle calls the endpoint and reflects the resulting state, and a logged-in visit to `Home` redirects to the dashboard.
