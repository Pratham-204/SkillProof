# 04 — Taxonomy versioning: re-verification forks a card on taxonomy change

**What to build:** An Evidence Card stays traceable to the taxonomy version that produced it — re-verifying under an unchanged taxonomy still overwrites in place, but re-verifying after the taxonomy has changed forks a new card instead of silently mutating the old one under different rules.

**Blocked by:** 01 (needs a versioned taxonomy to exist — can run in parallel with 02/03, since it only needs the version concept, not the new formula)

**Status:** done

- [x] Each Evidence Card records the `taxonomy_version` it was computed under.
- [x] Re-verifying a Candidate + Skill Tag under the same `taxonomy_version` as the existing card overwrites that card in place, exactly as before.
- [x] Re-verifying under a `taxonomy_version` newer than the existing card's creates a new card rather than mutating the old one.
- [x] `GET /evidence-card/{candidate_id}` returns only the latest `taxonomy_version` per Skill Tag by default.
