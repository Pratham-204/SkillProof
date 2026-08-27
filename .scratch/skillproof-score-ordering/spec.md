# Evidence Cards Sort by Confidence Score

Status: done

## Problem Statement

A Candidate's Evidence Cards — on their own Dashboard and on their public Evidence Card page — currently display in alphabetical order by Skill Tag name, an artifact of how the backend query happens to be ordered. That's not how a Candidate or a Recruiter actually wants to scan the list: the Candidate's strongest, most convincing evidence can be buried below a weak or even failed skill just because its name comes earlier alphabetically, undermining the whole point of a Confidence Score.

## Solution

Change the ordering both the Dashboard and the public Evidence Card page already consume from the shared `GET /evidence-card/{candidate_id}` endpoint: sort by Confidence Score descending instead of by Skill Tag name, with Skill Tag name as an alphabetical tie-break, and any `failed`-status card (which carries no meaningful score) sorted after every scored card. Because `ScanReveal`'s live scan/reveal animation builds its displayed list from the order its own SSE events arrive in — not from this endpoint's row order — this change is fully contained to the endpoint and reaches only the two already-complete, static views.

## User Stories

1. As a Candidate, I want my dashboard to show my strongest-scoring skills first, so my best evidence is immediately visible rather than buried alphabetically.
2. As a Recruiter viewing a public Evidence Card, I want the Candidate's strongest-scoring skills to appear first, so I can quickly gauge their best-supported claims without scanning the whole list.
3. As a Candidate with two skills at the same Confidence Score, I want a predictable, stable secondary ordering, so the list doesn't feel arbitrary or reshuffle between visits.
4. As a Candidate with a failed verification for one claimed skill, I want that card to sort to the bottom of my list, so the ranked ordering stays meaningful for the skills that do have a score.
5. As a Candidate mid-verification on the scan/reveal page, I want to keep seeing my skills reveal in the order they actually finish processing, so the live reveal experience isn't disrupted by this reordering.
6. As a developer, I want this reordering implemented once, at the single endpoint both the Dashboard and the public Evidence Card page already call, so the two views can never silently diverge in ordering.

## Implementation Decisions

- The endpoint that returns a Candidate's Evidence Cards changes its ordering from Skill Tag name ascending to Confidence Score descending, tie-broken by Skill Tag name ascending. A `status="failed"` card is always ordered after every card that has a real score, regardless of any nominal score value it happens to carry.
- No schema change — this is purely a change to how the existing query orders its results.
- No change to `ScanReveal` or its SSE-driven `scan`/`reveal`/`done` handling: it already builds its displayed list from event arrival order, not from this endpoint's row order, so it's unaffected by this change.
- No frontend change to the Dashboard or the public Evidence Card page: both already render cards in whatever order the endpoint returns them.
- One narrow, defensive frontend change surfaced during code review: `ScanReveal`'s `done` handler backfills any card that never fired an SSE `reveal` event (every `failed` card, since `verify_service._fail_card` never publishes `reveal`) directly from this endpoint's response — which, after this change, would have inherited its new score-order for that fallback list, contradicting the "`ScanReveal` is unaffected" claim below. Fixed by sorting that fallback list alphabetically by skill before it's appended, so `ScanReveal` no longer depends on this endpoint's ordering under any code path.
- `GET /search`'s multi-skill result ordering (by `average_score`, per ADR-0007) is a separate, already-correct concern and is untouched.

## Testing Decisions

A good test here asserts observable ordering of the response, not the query's internal implementation. Backend only — no frontend behavior changes, so no new frontend test coverage is needed.

- **Backend.** Same seam as the existing suite: drive the endpoint through the FastAPI `TestClient` (prior art: `tests/test_api_flow.py`'s existing Evidence Card assertions). New coverage:
  - Cards with distinct Confidence Scores come back highest-score-first.
  - Two cards at an equal Confidence Score come back in alphabetical-by-skill order.
  - A `failed` card comes back after every scored card, regardless of the other cards' scores.

## Out of Scope

- Any change to `ScanReveal`'s live reveal-order display.
- Any UI affordance letting a Candidate or Recruiter choose a different sort order — descending Confidence Score is the only order.
- Sorting within `GET /search`'s multi-skill results (already correct, unrelated to this spec).

## Further Notes

This spec was produced through a grilling session that also covered a cloud-deployment discussion and an embeddings-architecture change; see the separate `skillproof-embeddings-batching` spec for the latter. Deployment specifics (hosting provider, database, secrets) remain unresolved and are not part of this spec.
