# 06 — Recruiter search with Candidate opt-in

**What to build:** An unauthenticated, rate-limited search endpoint that ranks opted-in Candidates by Confidence Score for a given Skill Tag — with search visibility strictly opt-in and separate from direct Evidence Card access.

**Blocked by:** 01 (adds the `searchable` flag to Candidate), 04 (needs real Evidence Cards to search over).

**Status:** done

- [x] A `searchable` boolean column exists on the Candidate record, defaulting to `false`.
- [x] A Candidate can opt in to `searchable = true` (e.g. via a flag on `/verify` or a dedicated toggle) — never true by default.
- [x] `GET /search?skill=X&min_score=Y` returns only Candidates with `searchable = true` whose Confidence Score for that Skill Tag is ≥ `min_score`.
- [x] Results are sorted descending by Confidence Score and capped at a fixed limit — no pagination.
- [x] Each result includes the Candidate's GitHub profile link and their Evidence Card link.
- [x] `/search` requires no authentication and stores no per-recruiter state.
- [x] `/search` is rate-limited to 60 requests/minute per IP (slowapi); requests over the limit are rejected, not served.
- [x] A Candidate with `searchable = false` never appears in `/search` results regardless of score, but their direct Evidence Card link still works.

## Comments

Extended by `.scratch/skillproof-hybrid-scoring/spec.md`'s "`/verify` and `/search` surface changes": each result now also carries `evidence_type` (`declared_only` vs `verified`), and — following `.scratch/skillproof-hybrid-scoring/issues/04-taxonomy-versioning.md` — results dedupe to a candidate's latest `taxonomy_version` per skill so a taxonomy-version fork can't surface the same candidate twice.
