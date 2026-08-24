# SkillProof — Multi-Skill Search

Status: ready-for-agent

## Problem Statement

`/search` and its Recruiter-facing page only let a Recruiter filter by one Skill Tag at a time. A Recruiter looking for a candidate who has a specific combination of skills — a full-stack role needing React *and* Docker *and* Postgres, say — has no way to express that as a single query. They're forced to run one single-skill search per skill and manually cross-reference the result lists themselves, which doesn't scale past a couple of skills and throws away the per-skill evidence detail (Confidence Score, `evidence_type`) that makes an Evidence Card trustworthy in the first place.

## Solution

Extend `/search` to accept up to 8 Skill Tags per query, matched with AND semantics: a candidate appears only if they have a qualifying, searchable, complete Evidence Card for *every* selected skill. Each result carries a per-skill breakdown — `skill`, `confidence_score`, `evidence_type` for each of the queried skills — rather than collapsing to one flattened number, and results are ranked descending by the average of just those selected skills' scores (never diluted or inflated by skills outside the query). A `declared_only` card still satisfies its skill within the AND set rather than excluding the candidate outright; its low score pulls the candidate's average down on its own, and the visible per-skill `evidence_type` keeps a Recruiter from mistaking a bare manifest listing for real usage. The Recruiter search page's Skill Tag picker raises its selection cap from 1 to 8, reusing the same multi-select `SkillPicker` component already built for the claim-skills flow.

This also folds in a smaller, already-completed change to the same page: the `min_score` minimum-confidence filter (backend query param, schema field, and frontend input) has been removed entirely as unused surface area — see `CONTEXT.md`'s Recruiter term and Notes for current behavior.

## User Stories

**Recruiter — multi-skill filtering**

1. As a Recruiter, I want to search for candidates who have all of several specific skills at once, so I can filter directly for a role's required stack instead of manually cross-referencing separate single-skill searches.
2. As a Recruiter, I want each result to show its Confidence Score and `evidence_type` for every skill I searched on, so I can see exactly which parts of the stack are strong, weak, or merely declared — not one hidden aggregate number.
3. As a Recruiter, I want results ranked by how strong a candidate is across just the skills I searched for, so a candidate's unrelated strengths in other skills never inflate their position in this particular search.
4. As a Recruiter, I want a candidate with a `declared_only` skill among my selection to still appear (clearly flagged as such), rather than being silently excluded, so I don't miss a candidate who's strong across most of the stack but has one skill listed without usage history yet.
5. As a Recruiter, I want a clear cap on how many skills I can search on at once (up to 8), so the search stays scoped to a role's actual must-have stack rather than an open-ended filter.
6. As a Recruiter, I want a clear rejection — not a silent truncation — if I try to search more than 8 skills at once, so I understand why my query was refused rather than assuming a bug.
7. As a Recruiter, I want the skill picker to prevent me from selecting the same skill twice, so my query stays well-formed.

**SkillProof system**

8. As the SkillProof system, I want the existing per-skill "latest `taxonomy_version` per candidate" dedup applied independently to each selected skill before intersecting candidates, so a candidate re-verified under a bumped taxonomy version still can't appear twice or get incorrectly excluded from a multi-skill AND match.
9. As the SkillProof system, I want the AND-intersection query to still respect the existing `searchable` and `status = "complete"` filters per skill, so opted-out candidates and in-progress cards are never surfaced, exactly as in the single-skill case.
10. As the SkillProof system, I want the 8-skill cap and AND-matching enforced at the API boundary, not just the frontend picker, so the constraint holds for a direct API call that bypasses the UI.
11. As the SkillProof system, I want a duplicate skill passed twice in one query to be treated as a single occurrence (not double-counted toward the 8-skill cap or the ranking average), so a malformed or hand-built query degrades gracefully instead of erroring or skewing results.

## Implementation Decisions

**Query transport.** `GET /search` accepts `skill` as a repeated query parameter (`?skill=React&skill=Docker`), consistent with the existing single-skill contract and keeping the endpoint a plain, bookmarkable, idempotent GET — no switch to POST.

**8-skill cap.** More than 8 distinct skills in one query is rejected with 400, mirroring `/verify`'s existing 8-skill claims-per-call cap (see `CONTEXT.md` Notes). A repeated/duplicate skill value is deduplicated before the cap check and before scoring — it doesn't count twice toward the limit or the ranking average.

**AND-matching query.** For each selected skill, apply the existing "latest `taxonomy_version` per candidate for this skill" subquery (unchanged from the single-skill case), then intersect the qualifying-candidate sets across all selected skills. A candidate appears in results only when they have a qualifying, `searchable`, `status = "complete"` card for every one of them.

**Response schema.** `SearchResponse.skill: str` becomes `skills: list[str]`. `SearchResultOut` drops its flat `confidence_score`/`evidence_type` fields in favor of `matches: list[{skill, confidence_score, evidence_type}]` (one entry per selected skill) plus an explicit `average_score: float` field — the actual sort key, surfaced directly in the response rather than left implicit in result order.

**Ranking.** Results sort descending by `average_score`, defined as the mean of `confidence_score` across exactly the requested skills for that candidate — never averaged against any other skill the candidate has claimed but didn't search on. See ADR-0007 for the AND-vs-OR and average-vs-minimum reasoning.

**`declared_only` handling.** A `declared_only` card still satisfies its skill within the AND set; it is not treated as a non-match. See ADR-0007.

**Frontend.** `RecruiterSearch.tsx`'s `SkillPicker` `max` prop raises from `1` to `8` — the component itself needs no changes, since it already dedupes selections and supports `max > 1` (used elsewhere for the claim-skills flow). `api.ts`'s `searchCandidates` takes `skills: string[]` and sends them as repeated `skill` query params. The results list renders each candidate's per-skill breakdown (skill name, score, `evidence_type`) alongside `average_score`, reusing the existing solid-vs-dashed visual language from `lib/evidence.ts` (`evidenceCardClassName`, `evidenceTypeSummary`, `isWeakEvidence`) per matched skill rather than once per result.

## Testing Decisions

Same seam as the existing search tests — the FastAPI HTTP boundary via `TestClient`, driving `/search` directly in `tests/test_api_flow.py` (prior art: `test_search_returns_only_opted_in_candidates_sorted_by_score`, `test_search_dedupes_a_candidate_forked_across_taxonomy_versions`, `test_search_is_rate_limited_per_ip`). No new seams, no mocking of internals — real DB, real query logic.

New scenarios this feature needs beyond the existing single-skill coverage:

- A candidate matching *all* of 2+ selected skills appears in results; a candidate matching only *some* of them is excluded entirely — proves AND semantics.
- A candidate whose card for one selected skill is `declared_only` still appears, with that skill's entry in `matches` showing `evidence_type = "declared_only"` — proves declared_only isn't treated as a non-match.
- Two candidates whose ranking would flip depending on whether an out-of-query skill were wrongly folded into the average — proves `average_score` is computed over exactly the requested skills, not a candidate's full skill set.
- A query with 9 distinct skills is rejected with 400; a query with 8 succeeds.
- A query repeating the same skill value behaves identically to passing it once — doesn't trip the 8-skill cap, doesn't double-weight that skill in `average_score`.
- The existing taxonomy-version-fork dedup test (`test_search_dedupes_a_candidate_forked_across_taxonomy_versions`) extended to a 2-skill query, to confirm per-skill dedup still holds when intersecting.

Frontend changes are verified manually (`tsc -b`, `vite build`, `oxlint`, live click-through against a real multi-skill search) per the existing pattern in ticket 08 — no frontend test harness exists in this repo.

## Out of Scope

- **OR semantics as an alternate search mode** ("match any of these skills") — deferred; see ADR-0007's reversal trigger for when to revisit.
- **Any change to `/verify`'s existing 8-skill claims-per-call cap** — unrelated to and unaffected by this spec.
- **Saved searches, search history, or any Recruiter account state** — still out of scope per the MVP spec's original Recruiter scoping (ADR-0002).
- **Pagination beyond the existing hard result cap** — unchanged, not a design branch (see `CONTEXT.md` Notes).

## Further Notes

This spec extends `.scratch/skillproof-mvp/issues/06-recruiter-search-opt-in.md` and `.scratch/skillproof-frontend/issues/08-recruiter-search-page.md` rather than replacing them.

Full rationale for AND semantics, average-of-selected ranking, and `declared_only` inclusion lives in `docs/adr/0007-multi-skill-search-uses-and-semantics.md`. `CONTEXT.md`'s Recruiter term and Notes section reflect current behavior, including the removal of the `min_score` filter that preceded this spec in the same design session.
