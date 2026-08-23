# Taxonomy version changes fork Evidence Cards instead of always overwriting in place

CONTEXT.md's round-2 decision was that re-verification always overwrites a Candidate's existing Evidence Card per Skill Tag in place, with no history in MVP. That still holds for a same-taxonomy re-verify, but a taxonomy edit (a Detection Pattern or the scoring formula changing) would silently break "same input + same taxonomy → same score" reproducibility if an old card were mutated under a new taxonomy version. We decided to add `taxonomy_version` to the Evidence Card schema: re-verifying under a newer taxonomy version creates a new card rather than mutating the old one, while a same-version re-verify still overwrites in place exactly as before. `GET /evidence-card/{candidate_id}` returns only the latest version per Skill Tag by default.

## Consequences

This narrowly amends the round-2 "overwrite in place, no history" decision — full Evidence Card history is still out of scope for MVP; only a taxonomy version bump forks a card, not every re-verify.
