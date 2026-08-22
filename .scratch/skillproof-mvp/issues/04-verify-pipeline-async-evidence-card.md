# 04 — Verify pipeline: scoring → async Evidence Card generation

**What to build:** `POST /verify` triggers an asynchronous scoring pipeline that turns filtered evidence into Confidence Scores per claimed Skill Tag, persisted as Evidence Cards retrievable via `GET /evidence-card/{candidate_id}`. Also covers re-verification, since it's the same pipeline run again against the same Candidate.

**Blocked by:** 01, 02, 03.

**Status:** done

- [x] `POST /verify` accepts a `candidate_id` and a set of claimed Skill Tags and returns immediately — it does not block on scoring.
- [x] Scoring runs as an in-process background task: each Evidence Item's cosine similarity to the claimed Skill Tag's embedding is computed; items below 0.35 similarity don't count as evidence.
- [x] Confidence Score is the mean similarity of the top 5 qualifying items (fewer than 5 if fewer qualify — never padded), multiplied by a temporal multiplier (1.0 at ≥90 days of qualifying-evidence span, scaling linearly to 0.7 at 0 days, measured over the full qualifying set), clamped to [0,1].
- [x] A skill with zero qualifying evidence produces `confidence_score = 0`, `evidence_type = "none"`, `source_commits = []`.
- [x] `GET /evidence-card/{candidate_id}` reflects a "processing" state while the background job runs, and the real per-skill results once complete.
- [x] Calling `/verify` again for a Candidate overwrites their existing Evidence Card(s) per Skill Tag in place, reusing the already-stored GitHub token — no fresh OAuth redirect required.
- [x] If the stored token has been revoked, re-verification fails gracefully and the response indicates the Candidate needs to reconnect GitHub.

## Comments

The scoring formula (checklist item 3: pure embedding-similarity mean + temporal multiplier) was substantially rewritten by `.scratch/skillproof-hybrid-scoring/issues/02-hybrid-scoring-core-formula.md` (Presence/Volume/Depth/Span) and `.scratch/skillproof-hybrid-scoring/issues/03-anti-gaming-volume-depth.md` (anti-gaming corrections). The overwrite-in-place re-verify behavior (item 6) was narrowly amended by `.scratch/skillproof-hybrid-scoring/issues/04-taxonomy-versioning.md` to fork instead when the taxonomy version has changed. The async pipeline, evidence-card polling, and revoked-token handling (items 1, 2, 4, 5, 7) are unaffected and still current.
