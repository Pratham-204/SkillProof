# 01 — Sort Evidence Cards by Confidence Score descending

**What to build:** Change the ordering of the Candidate's Evidence Cards returned by the backend from alphabetical-by-Skill-Tag to Confidence-Score descending (alphabetical tie-break, failed cards last), so the Dashboard and the public Evidence Card page — both of which already consume this endpoint as-is — lead with the Candidate's strongest evidence instead of an alphabetical accident.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] The endpoint that returns a Candidate's Evidence Cards (`GET /evidence-card/{candidate_id}`) orders its `cards` list by `confidence_score` descending instead of by skill name.
- [x] Two cards with equal `confidence_score` come back ordered alphabetically by skill name (stable, predictable tie-break).
- [x] A card with `status="failed"` always sorts after every card that has a real score, regardless of any nominal score value it carries.
- [x] The existing latest-`taxonomy_version`-per-skill dedup behavior is unaffected — only the final ordering of the (already deduped) result set changes.
- [x] `ScanReveal`'s live reveal order (built from SSE `scan`/`reveal`/`done` events, not from this endpoint's row order) is unaffected — verify no code path in `ScanReveal` reads ordering from this endpoint's response. (Code review caught that this wasn't originally true: a skill that fails before ever firing a `reveal` event — `_fail_card` never publishes one — only ever arrives via the `done` handler's backfill of `evidence.cards`, which did inherit this endpoint's row order. Fixed with a one-line, alphabetical `.sort()` on that specific fallback list before it's appended, so `ScanReveal` no longer depends on this endpoint's ordering at all.)
- [x] Tested through the existing FastAPI `TestClient` seam (`tests/test_api_flow.py`) — not a new testing pattern.
