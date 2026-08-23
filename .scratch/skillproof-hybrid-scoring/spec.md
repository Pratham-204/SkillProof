# SkillProof — Hybrid Deterministic + Embedding Scoring

Status: ready-for-agent

## Problem Statement

SkillProof's MVP scores every claimed skill by comparing a Skill Tag's embedding directly against raw commit diffs and PR comments. That doesn't work well: the sentence-transformer model is trained on natural language, and source code embeds poorly against a plain-English skill description — so a Confidence Score can end up reflecting how well a diff happens to read as prose, not whether the Candidate actually used the skill. A Candidate who's done real, substantial work in a skill can score low simply because the model has no reliable way to recognize code; a well-worded but unrelated PR comment can score misleadingly high. That undermines the entire premise of an Evidence Card as something a Recruiter can trust.

## Solution

Replace the single embedding-similarity computation with four measurable Signals — Presence, Volume, Depth, and Span — each suited to what it's actually good at. Presence and Volume are exact, deterministic checks (is the dependency declared in a manifest? how many of the Candidate's own, PR-verified commits touch files matching the skill's Detection Pattern?) instead of approximate semantic comparison. Depth is the one Signal that keeps embeddings, and only where they're reliable: comparing natural-language PR comments and commit messages against the skill's canonical description — natural language against natural language. Span rewards sustained usage over a single burst, as before. Every Skill Tag in the taxonomy now carries a Detection Pattern (a package identifier, import pattern, API surface marker, config filename, or file extension); skills with no code footprint at all (System design, Security engineering, and similar practice skills) are removed from the claimable taxonomy until a future non-GitHub verification path exists for them. Two anti-gaming corrections are built into the formula from the start, not bolted on later: Volume only counts commits that are both Candidate-authored and, for repos the Candidate doesn't own, verifiably part of a PR they actually had merged — closing a fork-a-large-repo-and-claim-its-history gap. And Depth discounts a commit message's similarity relative to a PR review comment's, since a Candidate writes their own commit messages but not their own review threads.

## User Stories

**Candidate — scoring accuracy**

1. As a Candidate, I want my Confidence Score to reflect real usage of a skill rather than how well my code's prose happens to embed against a skill description, so legitimate technical work isn't underscored by an embedding model's blind spot for source code.
2. As a Candidate, I want a skill I've declared as a dependency and genuinely used in real commits to score higher than one I've only listed without ever touching, so demonstrated usage is rewarded over a bare manifest entry.
3. As a Candidate, I want a skill I've declared but never actually used in any commit to still show a small, clearly-labeled score rather than being indistinguishable from a skill with zero evidence at all, so a Recruiter can tell "listed" apart from "no evidence."
4. As a Candidate, I want a handful of unusually deep, technical commits or review discussions to count more than they would if diluted by averaging across every low-effort message, so genuinely strong evidence isn't washed out by noise.
5. As a Candidate, I want sustained usage of a skill over months to score higher than the same amount of evidence compressed into a single day, so consistent experience is reflected over a lucky burst.

**Candidate — anti-gaming and trust**

6. As a Candidate, I want my Volume Signal to only count commits I actually authored, and — for repos I don't own — only commits that were part of a PR I actually had merged, so forking a well-known repo can never inflate my score with someone else's work.
7. As a Candidate, I want my own commit messages to count less toward my Depth Signal than review comments other people engaged with, so writing an elaborate commit message on a trivial change isn't a viable way to inflate my score.
8. As a Candidate, I want gaming my score to cost more effort than it would save, so a verified Evidence Card actually means something to a Recruiter evaluating it.

**Candidate — taxonomy scope**

9. As a Candidate, I want to only be able to claim skills SkillProof can actually detect from my GitHub activity, so I'm never offered a claim that can never be verified.
10. As a Candidate, I want language skills (e.g. Python, Go) to be detected from the files I've actually written, not from a dependency line that doesn't apply to languages, so my core language usage is still recognized.
11. As a Candidate, I want a clear rejection — not a silent no-op — if I try to claim a skill that's been removed from the taxonomy pending a future non-GitHub verification path, so I understand why it's unavailable rather than assuming a bug.

**Candidate — reproducibility and re-verification**

12. As a Candidate, I want re-verifying under the same taxonomy version to still simply update my existing Evidence Card in place, so refreshing my card after new commits doesn't create clutter.
13. As a Candidate, I want re-verifying after the taxonomy itself has changed (a new or edited Detection Pattern, or a formula change) to produce a new, distinctly versioned card rather than silently rewriting the old one under different rules, so my score's meaning stays traceable to the taxonomy version that produced it.

**Recruiter**

14. As a Recruiter, I want to see whether a Candidate's evidence for a skill is real demonstrated usage or just a bare manifest listing, so I don't mistake a weak signal for a strong one.
15. As a Recruiter, I want the confidence score I filter search results by to mean the same thing across every candidate scored under the same taxonomy version, so results are actually comparable to each other.
16. As a Recruiter, I want search results to show me whether a match is "declared only" or "verified" evidence, so a low-but-real score from a permissive `min_score` filter isn't confused with a bare listing.

**Platform**

17. As the SkillProof system, I want every Skill Tag in the taxonomy to carry an explicit Detection Pattern, so Presence and Volume have something concrete to check against.
18. As the SkillProof system, I want Presence, Volume, and Span to be computed by plain deterministic code with no model or LLM involved, so those three Signals stay perfectly reproducible.
19. As the SkillProof system, I want Depth to remain the only Signal that touches an embedding model, and that model to stay local and free, so the LLM-free scoring guarantee (ADR-0001) holds even as the formula grows more sophisticated.
20. As the SkillProof system, I want a `taxonomy_version` recorded on every Evidence Card, so "same input + same taxonomy version → same score" stays true and a taxonomy change is never silently invisible.
21. As the SkillProof system, I want a Candidate's manifest files fetched and parsed once per repo, not once per claimed skill, so ingestion doesn't redundantly refetch the same file.
22. As the SkillProof system, I want the Signal weights and the anti-gaming discount/scoping rules to be simple named constants, so they can be recalibrated later (e.g. via logistic regression against outcome data) without restructuring the pipeline.
23. As the SkillProof system, I want the existing docs/config-only commit filter to not discard a file that is itself a registered Detection Pattern, so config-based detection evidence (e.g. a `Dockerfile`) isn't dropped before it's ever evaluated.
24. As the SkillProof system, I want `/verify` to reject a claim against a Skill Tag with no Detection Pattern the same way it already rejects an unknown Skill Tag, so the taxonomy's code-detectable-only scoping is enforced, not just documented.

## Implementation Decisions

**Confidence Score formula.** `confidence = 0.20×presence + 0.40×volume + 0.25×depth + 0.15×span`, all components bounded [0,1], weights sum to 1 (no clamping needed). `volume = n_commits / (n_commits + 5)` (BM25-style saturation). `span = span_days / (span_days + 90)`, measured over the full qualifying evidence set. `depth = mean(top_3(discounted_cosine_sims))` — the three highest similarity scores among Volume-qualifying items, each still subject to the existing 0.35 qualifying floor from the MVP. Weights and saturation constants are informed priors, not fitted; recalibration via logistic regression against outcome data (e.g. Technical Screen Pass Rate) is expected once such data exists, not a violation of this design.

**`evidence_type` gains a third state.** `"none"` (Presence = 0 and Volume = 0 — the skill is neither declared nor touched), `"declared_only"` (Presence = 1, Volume = 0 — listed but never used; produces a small Presence-only score, currently ≈0.20), `"verified"` (Volume > 0). This replaces the MVP's binary `none`/`verified` split.

**Detection Pattern.** New per-Skill-Tag data: `package_identifiers` (manifest dependency names), `import_patterns`, `api_surface_markers`, `config_filenames`, and — for language Skill Tags specifically — `language_extensions` (file extensions), plus the existing canonical description used for Depth's embedding. A Skill Tag with none of these authorable doesn't belong in the taxonomy. Presence checks manifest content and, for language skills, file extensions already seen across ingested commits (no separate repo-tree scan). Volume checks commit file paths/diff content against the pattern set.

**Taxonomy scope cut.** Skills with no authorable Detection Pattern — System design, Security engineering, Accessibility, Performance optimization, Event-driven architecture, Microservices architecture, and similar practice/theoretical entries — are removed from the claimable taxonomy for this pass. They're reserved for a future non-GitHub verification path (see Out of Scope) rather than left in, permanently stuck at zero. Authoring the final Detection Pattern set for the surviving entries is implementation work, not an open design question.

**Anti-gaming: Volume scoping.** For owned, non-fork repos, Volume counts commits filtered by `author = candidate` (unchanged from the MVP's ingestion). For external (non-owned) repos, Volume counts only commits that belong to a PR the Candidate actually opened and had merged in that repo — fetched per-merged-PR, not via a blanket author-filtered scan of the whole repo's history. This closes a fork-a-large-repo-and-claim-its-history gap that a blanket author filter alone doesn't prevent.

**Anti-gaming: Depth discount.** A commit message's cosine similarity is multiplied by a fixed discount (0.6) before entering `top_3` selection; a PR review comment's similarity is unaffected. Full exclusion of commit messages was considered and rejected — it would zero out Depth for solo/personal repos with no PR-review culture, exactly where a lot of real evidence lives.

**`GitHubClient` interface additions.** A method to fetch a repo's manifest files (the well-known set — `package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, `pom.xml`, etc. — 404s on missing files ignored), fetched once per repo. The existing external-repo commit-fetching path is restructured to iterate the Candidate's merged PRs in that repo and pull each PR's commit list directly, replacing the blanket `author=`-filtered repo-wide commit fetch.

**Taxonomy versioning.** `taxonomy_version` is added to the Evidence Card schema/record. A same-version re-verify still overwrites the existing card in place (unchanged MVP behavior). A re-verify under a bumped `taxonomy_version` creates a new card instead of mutating the old one. `GET /evidence-card/{candidate_id}` returns only the latest version per Skill Tag by default. This is a narrow amendment to the MVP's "always overwrite in place" rule — full Evidence Card history remains out of scope.

**`/verify` and `/search` surface changes.** `/verify` rejects a claim against a Skill Tag with no Detection Pattern (400), the same way it already rejects an unknown Skill Tag. `/search` results include `evidence_type` per result so a Recruiter can distinguish `declared_only` from `verified` without excluding either from results.

## Testing Decisions

Same one seam as the MVP (prior art: `tests/conftest.py`, `tests/test_api_flow.py`, `tests/test_scoring.py`, `tests/fixtures/github_fixtures.py`) — the FastAPI HTTP boundary via a test client, driving connect → verify → poll → evidence card → explain → search as one wired-together unit. The same two fakes at the same two external-system boundaries: `FakeGitHubClient` (extended with manifest-content and per-merged-PR-commit fixtures) and `FakeGroqClient` (unchanged). Presence, Volume, and Span are pure deterministic code over fixture data — run for real, never mocked, same treatment as embeddings already get for Depth.

New fixture scenarios this redesign needs, beyond what the MVP suite covers: a repo with a manifest-declared-but-never-touched dependency, to prove the `declared_only` path; a repo where the Candidate has author-matching commits that are *not* part of any of their merged PRs, to prove Volume correctly excludes them (the fork-and-fake regression test); a PR review comment and an equivalent-content commit message on the same skill, to prove the 0.6 Depth discount actually lands in the score; two `/verify` runs against the same candidate+skill under two different `taxonomy_version`s, to prove card-forking rather than in-place overwrite.

## Out of Scope

- **Self-extending taxonomy** — parsing unknown manifest packages, proposing new Detection Patterns via an LLM, human approval gate before an entry enters the scored path. Deferred to its own future spec.
- **Depth Interview** — an unscored, LLM-conducted conversational artifact (code-anchored, probing a specific commit; or experience-anchored, probing a Candidate's self-described private/internship work). Deferred to its own future spec; this is also where the taxonomy's removed theoretical/practice skills are expected to eventually become claimable again.
- **Multi-platform evidence sourcing** (LeetCode, HackerRank, etc.) — not yet scoped at all, noted only as a future direction.
- **Firecrawl-based extraction** — tabled pending a concrete target use case; likely only relevant to the deferred self-extending-taxonomy feature, not this pass.
- **Graph database / vector database introduction** — no concrete query need was identified that the existing relational schema plus in-memory embedding comparison can't already serve.
- **Recalibrating formula weights/constants against real outcome data** — explicitly deferred until such data exists; today's constants are informed priors.
- **Full Evidence Card history/versioning** beyond the narrow `taxonomy_version` fork — a same-version re-verify still overwrites in place.

## Further Notes

This spec revises `.scratch/skillproof-mvp/spec.md`'s scoring and taxonomy sections rather than replacing the MVP wholesale. Of the original six issues: 02 (taxonomy) and 04 (verify pipeline/scoring) are substantially rewritten by this spec; 03 (ingestion) is extended (manifest fetching, PR-scoped external commit fetching); 06 (search) gets a small extension (`evidence_type` exposure); 01 and 05 are unaffected.

Full design history and rationale live in `CONTEXT.md` (rounds 2 through 6) and two ADRs at the repo root: `docs/adr/0004-hybrid-deterministic-and-embedding-scoring.md` (the Signal formula and both anti-gaming corrections) and `docs/adr/0005-taxonomy-version-forks-evidence-cards.md` (the versioning amendment) — worth reading alongside this spec for the "why" behind each decision above.
