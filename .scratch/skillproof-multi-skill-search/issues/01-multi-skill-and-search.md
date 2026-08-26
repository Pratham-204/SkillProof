# 01 — Multi-skill AND search

**What to build:** `/search` and its Recruiter-facing page accept up to 8 Skill Tags per query with AND semantics — a candidate must have a qualifying Evidence Card for every selected skill to appear — showing each candidate's per-skill breakdown and ranking by the average of just the selected skills.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `GET /search` accepts `skill` as a repeated query parameter (up to 8 distinct values); more than 8 distinct values is rejected with 400.
- [x] A result includes a candidate only if they have a qualifying, `searchable`, `status="complete"` Evidence Card for every selected skill (AND), respecting the existing per-skill `taxonomy_version` dedup (latest version per candidate per skill).
- [x] A `declared_only` card for a selected skill still counts as a match — it is not excluded from AND results.
- [x] Each result exposes a per-skill breakdown (`skill`, `confidence_score`, `evidence_type` for every selected skill) plus an explicit `average_score` computed only over the selected skills (never a candidate's other claimed skills).
- [x] Results sort descending by `average_score`.
- [x] A duplicate skill value in the query is treated as a single occurrence — doesn't trip the 8-skill cap or double-weight the average.
- [x] The Recruiter search page's Skill Tag picker allows selecting up to 8 skills and renders each result's per-skill breakdown and average score, reusing the existing verified/`declared_only` visual language (`lib/evidence.ts`).
- [x] Backend tests cover: AND-exclusion of partial matches, `declared_only` inclusion, `average_score` computed over only the queried skills (not a candidate's full skill set), 8-skill cap rejection (400), duplicate-skill handling, and the existing taxonomy-version-fork dedup extended to a 2-skill query.

## Comments

Full design rationale: `docs/adr/0007-multi-skill-search-uses-and-semantics.md`. Spec: `.scratch/skillproof-multi-skill-search/spec.md`. Test seam: the existing FastAPI `TestClient` boundary in `tests/test_api_flow.py` (prior art: `test_search_returns_only_opted_in_candidates_sorted_by_score`, `test_search_dedupes_a_candidate_forked_across_taxonomy_versions`) — no new seams. Frontend verified manually (`tsc -b`, `vite build`, live click-through), no frontend test harness in this repo.
