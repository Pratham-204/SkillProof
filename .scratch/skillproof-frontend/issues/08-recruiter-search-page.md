# 08 — Recruiter search page

**What to build:** An unauthenticated page over `GET /search`, letting a Recruiter filter by skill and minimum confidence and see ranked, linked results.

**Blocked by:** 02.

**Status:** done

- [x] Search form: a Skill Tag selector (same autocomplete source as ticket 04, `GET /skills`) and a minimum-confidence input.
- [x] Results render sorted descending by confidence exactly as the API returns them (no client-side re-sorting), each showing `evidence_type` distinctly (so `declared_only` isn't visually confused with `verified`, matching CONTEXT.md's stated intent for that field).
- [x] Each result links to the Candidate's GitHub profile and to their public Evidence Card page (ticket 07's `/c/:candidateId` route).
- [x] No login/account affordance appears anywhere on this page — matches the backend having no Recruiter auth model at all (ADR-0002).
- [x] A rate-limited (429) response from `/search` shows a clear "try again shortly" state rather than an unhandled error.

## Comments

**Implementation:** `RecruiterSearch.tsx` reuses `components/SkillPicker.tsx` (ticket 04) with `max={1}` for single-skill selection — no new autocomplete component needed, since `SkillPicker`'s chip/selected-array API degenerates cleanly to a single choice. A plain `<input type="number" min={0} max={1} step={0.05}>` covers minimum confidence. Submitting calls `searchCandidates(skill, minScore)` (`api.ts`, already built in ticket 04) and renders `results` in the exact order returned — no `.sort()` anywhere in this component. Each result reuses the same solid-vs-dashed-border visual language as `EvidenceCardTile` (`evidence_type !== 'verified'` → dashed/muted) for consistency across the app, links `github_login` to `github_profile_url` (real GitHub, `target="_blank"`), and links "View Evidence Card" to the frontend's own `/c/{candidate_id}` route via `react-router-dom`'s `Link` — deliberately *not* the API's `evidence_card_url` field (that points at the raw JSON endpoint, not the frontend page). `RateLimitedError` (already thrown by `searchCandidates` for a 429) is caught and shown as a distinct "Too many searches — try again shortly" state, separate from the generic error state.

**Verified live:** searched "Python" against the real account created in tickets 04/05 — returned the real `Pratham-204` result at 27%/`verified`, clicked "View Evidence Card" and landed on ticket 07's page via client-side routing (no full reload). `tsc -b`, `vite build`, `oxlint` all clean.
