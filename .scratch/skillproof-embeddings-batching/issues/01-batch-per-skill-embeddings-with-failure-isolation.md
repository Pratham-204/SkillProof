# 01 — Batch per-skill embeddings calls, isolate failures per skill

**What to build:** `score_skill()` currently calls the embeddings backend once per matching Evidence Item, in a per-item loop. Change it to collect one skill's matching items and issue a single batched embeddings call instead — a prerequisite for any future embeddings backend with real per-call (e.g. network) overhead. If that batched call fails, mark only that skill's Evidence Card as failed and continue scoring the rest of the run's claimed skills, rather than aborting the whole run.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `score_skill()` issues one batched embeddings call per skill (covering every Evidence Item that already matches that skill's Detection Pattern) instead of one call per matching item.
- [x] For a given `EvidenceBundle` and skill, the batched version produces a `ConfidenceResult` identical to today's per-item version — this restructuring changes zero computed scores. (Proven by the full pre-existing `tests/test_scoring.py` suite continuing to pass unchanged, plus a new test with two items of deliberately different similarity in the same batched call, to catch an index-misalignment bug the equivalence tests alone wouldn't.)
- [x] The verification pipeline's existing per-skill loop (one `score_skill()` call per claimed skill) is unchanged; `score_skill()` remains self-contained and per-skill.
- [x] If a skill's batched embeddings call fails, that skill's Evidence Card is set to `status="failed"` with a clear, actionable error message (matching the style of the existing GitHub-auth/token-decryption failure messages), while every other claimed skill in the same run still scores and completes normally.
- [x] `FakeEmbeddingsBackend` (the existing test seam) is extended with a minimal way to simulate a failure (e.g. raise for configured texts/skills), used to test the failure-isolation behavior — an additive extension of the existing fake-backend seam, not a new testing mechanism.
- [x] Covered by: a `tests/test_scoring.py`-level test proving score-equivalence between the old and new call shape, a dedicated test asserting exactly one batched call is made per skill (not one per item), and two `tests/test_api_flow.py`-level `TestClient` tests proving isolation — one where the sibling skill has no matching evidence at all (embed_batch never called for it), and a stronger one where the sibling's own embed_batch call also genuinely executes and succeeds. (Code review flagged that the shared GitHub fixture only ever produces genuine matching evidence for one skill, so the first isolation test alone couldn't prove isolation between two *active* batches — the second test hand-builds evidence for two skills to close that gap.)
