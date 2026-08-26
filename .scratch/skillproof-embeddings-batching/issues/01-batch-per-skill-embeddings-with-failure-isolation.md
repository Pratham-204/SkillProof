# 01 — Batch per-skill embeddings calls, isolate failures per skill

**What to build:** `score_skill()` currently calls the embeddings backend once per matching Evidence Item, in a per-item loop. Change it to collect one skill's matching items and issue a single batched embeddings call instead — a prerequisite for any future embeddings backend with real per-call (e.g. network) overhead. If that batched call fails, mark only that skill's Evidence Card as failed and continue scoring the rest of the run's claimed skills, rather than aborting the whole run.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `score_skill()` issues one batched embeddings call per skill (covering every Evidence Item that already matches that skill's Detection Pattern) instead of one call per matching item.
- [ ] For a given `EvidenceBundle` and skill, the batched version produces a `ConfidenceResult` identical to today's per-item version — this restructuring changes zero computed scores.
- [ ] The verification pipeline's existing per-skill loop (one `score_skill()` call per claimed skill) is unchanged; `score_skill()` remains self-contained and per-skill.
- [ ] If a skill's batched embeddings call fails, that skill's Evidence Card is set to `status="failed"` with a clear, actionable error message (matching the style of the existing GitHub-auth/token-decryption failure messages), while every other claimed skill in the same run still scores and completes normally.
- [ ] `FakeEmbeddingsBackend` (the existing test seam) is extended with a minimal way to simulate a failure (e.g. raise for configured texts/skills), used to test the failure-isolation behavior — an additive extension of the existing fake-backend seam, not a new testing mechanism.
- [ ] Covered by: a `tests/test_scoring.py`-level test proving score-equivalence between the old and new call shape, a dedicated test asserting exactly one batched call is made per skill (not one per item), and a `tests/test_api_flow.py`-level `TestClient` test proving one skill's simulated embeddings failure produces a `failed` card while a sibling claimed skill in the same run still comes back `complete`.
