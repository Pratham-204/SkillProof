# Batch and Isolate Embeddings Calls; Generalize the Taxonomy Cache

Status: ready-for-agent

## Problem Statement

Scoring a Skill Tag calls the embeddings backend once per matching Evidence Item, in a plain per-item loop, for every claimed Skill Tag in a verification run. That's harmless today because the active backend is a local, in-process `sentence-transformers` model with no per-call network cost. But it's structured in a way that would make any future embeddings backend with real per-call overhead — specifically, a hosted embeddings API being considered to reduce production RAM footprint — prohibitively slow and expensive: a verification run with even a modest number of matching commits and PR comments would turn into dozens to hundreds of individual network round trips.

Two related gaps compound this: the taxonomy's Skill Tag description embeddings are only disk-cached when the active backend is specifically the local `SentenceTransformerBackend` class, so any other real backend would silently re-embed the entire taxonomy on every process restart. And nothing today would protect an Evidence Card's reproducibility guarantee (ADR-0005 — "same input + same taxonomy → same score") if the active embeddings backend or model ever changed: a re-verify right after such a change would silently overwrite an existing card with a score computed in a different embedding space, under a `taxonomy_version` that's supposed to guarantee comparability.

## Solution

Restructure the scoring path so a skill's embedding calls are batched into one call instead of one-per-item, with one skill's batch failure isolated from the rest of the run, and generalize the taxonomy's disk cache so it isn't hardcoded to one specific backend class. All of this is built and proven against the existing local backend — this spec is a pure internal restructuring with zero change to computed Confidence Scores, making a future backend swap viable without being the swap itself. Choosing a hosted provider, writing a real hosted backend, and executing the swap are separate, later work.

## User Stories

**Correctness and behavior preservation**

1. As a Candidate, I want my Confidence Scores to compute identically to how they do today, so this internal restructuring never changes what score I actually get.
2. As a developer, I want this restructuring fully covered by the existing scoring test seam, so a regression in the batching logic is caught the same way any other scoring regression already is.

**Batching**

3. As a developer, I want `score_skill()` to gather one skill's qualifying Evidence Items into a single batched embeddings call instead of one call per item, so a future network-bound embeddings backend doesn't turn one verification run into dozens of sequential round trips.
4. As a developer, I want the existing per-skill calling convention in the verification pipeline (one `score_skill()` call per claimed skill, in a loop) left unchanged, so this stays a minimal, reversible, self-contained restructuring rather than a bigger pipeline redesign.

**Failure isolation**

5. As a Candidate verifying multiple skills, I want one skill's embeddings-call failure to only fail that skill's card, so a transient problem scoring one claimed skill doesn't wipe out the results for every other skill in the same run.
6. As a developer debugging a failed card, I want its error message to follow the same clear, actionable style already used for GitHub auth/token-decryption failures, so failure messages stay consistent across the whole verification pipeline.

**Cache generalization**

7. As a developer, I want the Skill Tag description embeddings' disk cache to work for any embeddings backend, not just the current local model, so a future backend swap doesn't silently force re-embedding the entire taxonomy on every process restart.
8. As a developer, I want the disk cache to detect a change in which backend produced it and invalidate itself accordingly, so a stale cache from a different embedding space is never silently reused.

**Future reproducibility (planned, not executed here)**

9. As a developer, I want a documented plan for treating a future embeddings backend/model change as a taxonomy-version-forking event, so when that change actually happens, "same input + same taxonomy → same score" (ADR-0005) still holds instead of silently breaking.

## Implementation Decisions

- **Batching granularity.** `score_skill()`'s per-item embedding lookup changes from one call per matching Evidence Item to one batched call per skill: collect the text of every Evidence Item that already matches that skill's Detection Pattern first, issue a single batched embeddings call across all of them, then proceed with the existing qualifying-floor, discount, and top-N Depth logic against the returned vectors exactly as today. This is per-skill batching, not whole-run batching — the bigger, cross-skill deduplicated-batching structural change is explicitly not part of this spec (see Out of Scope).
- **Calling convention unchanged.** The verification pipeline's existing per-skill loop (one `score_skill()` call per claimed skill) is untouched — `score_skill()` stays a self-contained, per-skill function.
- **Failure isolation.** If a skill's batched embeddings call fails (raises), that skill's Evidence Card is marked `status="failed"` with a clear, actionable error message, following the existing failed-card convention already used for GitHub auth and token-decryption failures. Processing continues to the next claimed skill in the same run rather than aborting the whole run.
- **Cache generalization.** The taxonomy's Skill Tag description embeddings disk cache — currently gated on "is the active backend specifically the local `SentenceTransformerBackend` class" — is generalized to cache for any real (non-test-fake) backend, with the cache keyed or otherwise checked so a change in the active backend/model is detected and never silently serves a stale, incompatible-embedding-space cache.
- **No new backend in this pass.** No hosted embeddings backend is added, and no provider is chosen. The only backend exercised by this work is the existing local `SentenceTransformerBackend`, alongside the existing test-only fake backend.
- **Future cutover plan (documented here, executed later).** At the point a future change actually swaps the active embeddings backend or model, the Skill Tag taxonomy's version is bumped as part of that change, reusing the existing ADR-0005 fork-on-version-change machinery so affected Evidence Cards fork instead of being silently overwritten with a score from a different embedding space. ADR-0005 gets a short amendment at that time documenting that an embedding backend/model change counts as a taxonomy-version-forking event. Neither the version bump nor the ADR amendment happens as part of this spec — there is no backend change happening yet to bump a version for.

## Testing Decisions

A good test here asserts observable behavior (the score produced, the card status, the cache's read/write outcome) rather than internal call mechanics — except where the whole point of a test is proving the batching structure itself, which is called out explicitly below.

- **Batching correctness.** Existing unit-test seam for scoring (`tests/test_scoring.py`, calling `scoring.score_skill(bundle, skill)` directly against an `EvidenceBundle`, using the existing `fake_embeddings` fixture where exact vectors matter). Prove batching produces identical `ConfidenceResult`s to today's per-item calls for the same inputs. One dedicated test should also assert that a single batched call is made per skill (not one per item) — the behavioral score-equivalence tests alone wouldn't catch an accidental revert to per-item calls.
- **Failure isolation.** HTTP-level seam matching existing precedent (`tests/test_api_flow.py`'s GitHub-auth-failure tests, which assert `body["cards"][0]["status"] == "failed"`): claim two skills where one skill's embeddings call is made to fail and the other succeeds normally; assert one card comes back `failed` with an error message and the other comes back `complete` with a real score.
- **Cache generalization.** Existing seam (`tests/test_embeddings.py`, which already tests the disk-cache bypass/restore behavior against `FakeEmbeddingsBackend` and `SentenceTransformerBackend`). Extend it with a case proving the cache is invalidated when the active backend/model changes, not hardcoded to recognize only one specific class.
- **New, minimal test seam.** `FakeEmbeddingsBackend` currently has no way to simulate a failure. A small, additive extension (e.g. an optional "raise for these texts/skills" configuration) is needed to test failure isolation. This extends the existing fake-backend seam already used throughout the embeddings/scoring/taxonomy tests — it is not a new testing mechanism.

## Out of Scope

- Choosing a hosted embeddings provider, or writing any real hosted `EmbeddingsBackend` implementation.
- Actually switching the active embeddings backend, provisioning a provider API key, or performing the taxonomy-version bump / ADR-0005 amendment described in Implementation Decisions — that's planned here, executed at cutover time, as its own future piece of work.
- Any cloud hosting or deployment work (Railway project setup, managed Postgres provisioning, a production GitHub OAuth App, a custom domain) — deliberately deferred pending a further grilling round; not part of this spec.
- Adopting Create T3 App or any Next.js-based rewrite — explicitly ruled out for this project.
- Whole-run, cross-skill deduplicated batching (embedding each unique Evidence Item once across all claimed skills rather than per skill) — per-skill batching was chosen as the simpler, more reversible first step.

## Further Notes

This spec was produced through a grilling session that also covered Evidence Card display ordering (see the separate `skillproof-score-ordering` spec) and a cloud-deployment discussion. The deployment discussion settled on: Railway as the hosting platform, a ~$5/mo budget, a managed Postgres database (moving off SQLite), a platform-issued subdomain to start, and native auto-deploy on push to `main` — but it surfaced that a `sentence-transformers`-based process likely can't fit that budget alongside Postgres, which is what motivated this batching/architecture work as a prerequisite for eventually moving to a hosted embeddings backend. Provider selection and the actual Railway execution (secrets, OAuth App, Postgres provisioning) still need their own grilling round before they're ready to spec.

Note also that switching to a hosted embeddings API would reverse part of ADR-0001 ("scoring stays deterministic and LLM-free... computed entirely by local sentence-transformer embeddings... free to compute") — that ADR will need its own amendment at the point the actual backend swap happens, alongside the ADR-0005 amendment already noted above.
