# Multi-skill search uses AND semantics, ranked by the average of only the selected skills

`/search` moves from one Skill Tag per query to up to 8. AND was chosen over OR: a Recruiter combining Skill Tags is almost always looking for a candidate who has the whole stack ("React and Docker"), not a wider net across unrelated skills ("React or Docker") — the latter is just several single-skill searches merged client-side and doesn't need product support. Each result carries a per-skill breakdown (`skill`, `confidence_score`, `evidence_type` for every selected skill) rather than collapsing to one number, consistent with the product's existing refusal to smooth a weak signal into a flattering aggregate (ADR-0004's `declared_only` distinction, round 6's "a real, honestly-computed low score stays visible"). Results are ranked descending by the average of the selected skills' scores only — never averaged against skills outside the query — so adding an unrelated strong skill to a candidate's profile can't inflate their rank for a search that didn't ask about it. A `declared_only` Evidence Card still counts as satisfying a skill within the AND set rather than excluding the candidate outright; its low score pulls the candidate's average down on its own, and the visible `evidence_type` keeps a Recruiter from mistaking a bare manifest listing for real usage.

## Considered Options

OR semantics (union across selected skills) — rejected: doesn't match how a Recruiter actually uses a multi-select filter, and is trivially reconstructed by running separate single-skill searches if ever needed.

Ranking by the minimum score across selected skills ("weakest link") instead of the average — considered as the stricter, more conservative option, but rejected in favor of average: a single thin skill in an otherwise strong profile shouldn't dominate the ranking the way a minimum would.

Excluding candidates with any `declared_only` skill in the selected set — rejected as inconsistent with the existing round-6 principle that `declared_only` results stay visible rather than silently gated.

## Reversal trigger

If Recruiters start asking for a broader "any of these skills" mode, OR semantics would need to be added as an explicit second mode (e.g. a `match` query param) rather than replacing AND — both are legitimate, distinct searches.
