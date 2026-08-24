# SkillProof — Self-Extending Taxonomy

Status: ready-for-agent

## Problem Statement

SkillProof's taxonomy is a static, hand-curated list of ~109 Skill Tags. A Candidate whose real GitHub work uses a genuine technology that simply hasn't been added yet has no way to claim it — no Presence, Volume, or Depth Signal can ever be computed for a skill that doesn't exist in the taxonomy, no matter how much real evidence exists for it. Manual curation doesn't scale with how fast the real-world technology landscape moves, and CONTEXT.md's round-2 decision already ruled out adopting an external taxonomy standard as a source of truth — external taxonomies don't respect SkillProof's actual constraint, that a Skill Tag only belongs if it carries an authorable Detection Pattern. The taxonomy needs a way to grow itself from what Candidates are actually using, without becoming a slow, manually-bottlenecked review queue.

## Solution

Two new pieces layered onto the existing pipeline. First, `/verify`'s ingestion step — which already fetches each repo's manifest content once per repo — now also records a Sighting whenever a manifest declares a package that matches no existing Skill Tag's Detection Pattern. This is a cheap diff against the current taxonomy; no LLM call, no added latency to `/verify`. Second, a separate batch job, run on a fixed cadence (e.g. nightly) rather than continuously, evaluates accumulated Sightings: once a given (ecosystem, package) pair has been sighted across enough distinct Candidates to be worth considering, it's checked against the package's real ecosystem registry (does it actually exist?), checked for exact and semantic duplication against the existing taxonomy, and then handed to an LLM that either drafts a new Skill Tag (category, from the taxonomy's fixed five, plus a canonical description — everything else is derived mechanically from the Sighting itself) or abstains. Anything the LLM drafts publishes directly, with no human approval step (ADR-0008) — publishing is batched specifically to bound how often the global `taxonomy_version` counter bumps, since a bump forks every Candidate's Evidence Cards (ADR-0005), not just the ones for the newly added skill.

## User Stories

**Candidate**

1. As a Candidate, I want a real technology I've genuinely used but that isn't yet in SkillProof's taxonomy to eventually become claimable without anyone having to manually notice and add it, so my actual work isn't permanently invisible to Evidence Cards.
2. As a Candidate, I want my `/verify` call to stay exactly as fast as it is today even though it's now also recording unrecognized packages, so taxonomy growth never costs me latency.
3. As a Candidate, I want a package that's genuinely obscure or private to me alone to not spawn a new Skill Tag just because I mentioned it once, so the taxonomy doesn't fill up with noise from a single candidate's idiosyncratic dependencies.
4. As a Candidate, I want a newly published Skill Tag to be immediately available for me to claim on my next `/verify` call, so I don't have to wait on anything beyond the taxonomy actually publishing.
5. As a Candidate re-verifying after a taxonomy update, I want the same `taxonomy_version`-forking behavior that already governs manual taxonomy edits to apply here too, so an automatically-added skill doesn't silently invalidate my existing Evidence Cards' reproducibility guarantee.

**Recruiter**

6. As a Recruiter, I want the taxonomy I search against to expand over time as real technologies gain adoption among candidates, so my search coverage doesn't stay frozen at whatever was hand-curated at launch.

**Platform / system**

7. As the SkillProof system, I want to record a Sighting (ecosystem, package name, candidate, repo) for any manifest-declared package matching no existing Skill Tag, at the point ingestion already parses manifest content, so no new fetch or parse work is introduced.
8. As the SkillProof system, I want Sightings to accumulate per (ecosystem, package) pair across distinct Candidates, so a single candidate's one-off dependency can never alone trigger a taxonomy addition.
9. As the SkillProof system, I want a batch process — not `/verify` itself — to evaluate Sightings and publish new Skill Tags, so no LLM call or network round-trip is ever on the request path of a Candidate's verification.
10. As the SkillProof system, I want that batch process to run on a fixed cadence rather than continuously, so publishing frequency stays bounded and so does how often the global `taxonomy_version` bump forks every Evidence Card.
11. As the SkillProof system, I want a Sighting's (ecosystem, package) pair confirmed to exist on its real ecosystem registry before an LLM is ever asked to draft anything, so registry-nonexistent or typo'd packages are rejected for free, before spending an LLM call.
12. As the SkillProof system, I want a Sighting rejected as an exact or case-insensitive name duplicate of an existing Skill Tag before an LLM is asked to draft anything, so the cheapest possible check catches the most obvious duplicate case first.
13. As the SkillProof system, I want the LLM's duplicate check to also compare a Sighting against every existing Skill Tag's canonical description, not just its name, so a differently-named package that's really the same underlying skill (e.g. a database driver package vs. the database itself) doesn't produce a redundant entry.
14. As the SkillProof system, I want the LLM able to output "not a real claimable skill" for a Sighting that clears the deterministic checks but still isn't a good fit, so it's never forced to invent an entry for something that doesn't deserve one.
15. As the SkillProof system, I want the LLM's category choice constrained to the taxonomy's existing five categories, so it can never introduce a new, potentially near-duplicate category label.
16. As the SkillProof system, I want a published Skill Tag's Detection Pattern populated directly from the Sighting that produced it (the sighted ecosystem + package name as its `manifest_packages` entry), with the LLM only responsible for category and canonical description, so nothing in the Detection Pattern itself depends on an LLM's judgment.
17. As the SkillProof system, I want a Sighting group that's already been evaluated (published, rejected as duplicate, or abstained on) to never be re-evaluated on a later batch run just because it's sighted again, so the batch job's LLM/registry calls don't grow unbounded as the same package keeps showing up.
18. As the SkillProof system, I want `taxonomy_version` to bump exactly once per batch run that publishes at least one new Skill Tag, not once per tag published within that run, so a run that adds several tags at once still only forks each existing Evidence Card once.
19. As the SkillProof system, I want a Skill Tag published by the batch job to be indistinguishable, from every existing code path's perspective (scoring, `/verify`, `/skills`, `/search`), from a hand-curated entry, so no new special-casing is needed anywhere outside the taxonomy-growth code itself.
20. As the SkillProof maintainer, I want a bad auto-published entry correctable via the exact same manual `skills.json` edit and version bump used for any hand-curated correction today, so no dedicated retraction tooling has to be built for this pass.

## Implementation Decisions

**Sighting.** New persisted record: `(ecosystem, package_name, candidate_id, repo, seen_at)`. Written during `ingest_evidence()` for every manifest-declared package matching none of the current taxonomy's `manifest_packages` Detection Pattern entries — a diff against `taxonomy.list_skills()` using data already fetched, no new parsing work. Not evidence, never scored, never exposed through any API response.

**Threshold.** A (ecosystem, package_name) pair becomes eligible for the batch job once it has Sightings from at least N distinct `candidate_id`s. N is a named constant, not hardcoded inline — an informed prior, not fitted; recalibration is expected once real sighting volume exists, the same posture as the Confidence Score's weights and saturation constants.

**Batch job (`taxonomy_growth.publish_new_skill_tags`).** One new function, invoked from a scheduled entry point (the scheduling mechanism itself — which cron/scheduler, exact cadence — is deployment configuration, out of scope here). Takes an injected `RegistryClient`, the existing `GroqClient`, and a DB session. Per eligible (ecosystem, package_name) pair, in order: (1) skip if this pair is already decided (published/rejected/abstained — tracked so repeats don't reprocess); (2) `RegistryClient.exists(ecosystem, package_name)` — skip if false; (3) exact/case-insensitive name dedup against `taxonomy.list_skills()` — skip if matched; (4) `GroqClient.draft_skill_tag(package_name, ecosystem, existing_skills) -> SkillTagDraft | None` — the LLM checks semantic duplication against every existing entry's description and may return `None` to abstain; (5) if a draft is returned, append it to `skills.json` (name, a category from the fixed five, description, `detection.manifest_packages = [{ecosystem, package_name}]`) and mark the pair decided. After the loop, if anything published this run, bump `skills.json`'s `version` exactly once.

**`RegistryClient` (new).** Abstract base with `exists(ecosystem: str, package_name: str) -> bool`, mirroring the existing `GitHubClient`/`GroqClient` shape. `RealRegistryClient` hits the relevant ecosystem's public registry API per `ecosystem` (npm registry, PyPI JSON API, etc.) — scoped to whichever ecosystems the current taxonomy's `manifest_packages` entries already reference; no new ecosystem support introduced. `FakeRegistryClient` holds a fixed `known: set[tuple[str, str]]`, matching `FakeGitHubClient`/`FakeGroqClient`'s existing fake style.

**`GroqClient` gains `draft_skill_tag`.** New abstract method alongside the existing `generate_explanation`: `draft_skill_tag(package_name: str, ecosystem: str, existing_skills: list[SkillTag]) -> SkillTagDraft | None`. `SkillTagDraft` is a small new frozen dataclass (`name`, `category`, `description`) — a category the LLM returns outside the fixed five is treated as an abstain, not trusted verbatim. `RealGroqClient` implements it as a second prompt using the same model/`httpx` call shape as `generate_explanation`. `FakeGroqClient` gets a configurable `draft_response: SkillTagDraft | None` alongside its existing `canned_response`/`should_fail`.

**No new embeddings work needed.** `taxonomy._embeddings_cache()` already recomputes and re-persists whenever the cached skill-name list doesn't match the current taxonomy's names — a newly published entry gets its embedding for free on next access, via the self-healing path that already exists today. Confirming existing behavior already covers this, not a new decision.

**`taxonomy_version` semantics unchanged from ADR-0005.** No schema change to `EvidenceCard` or to what the taxonomy file's `version` field means — the batch job increments the same integer a manual hand-edit already would.

**Process/deploy note.** `taxonomy._taxonomy_file()` is `@lru_cache`d with no invalidation — a running app process won't see a `skills.json` change, manual or batch-published, until it restarts. This is existing, unrelated behavior; whatever deploy/restart cadence already applies to hand-curated taxonomy edits applies here too.

## Testing Decisions

Two seams, matching the two new pieces:

Sighting recording rides the existing seam (prior art: `tests/test_api_flow.py`, `FakeGitHubClient`) — a `/verify` call against a `FakeGitHubClient`-controlled repo whose manifest declares a package matching no taxonomy entry, asserting a Sighting exists afterward with the right `(ecosystem, package_name, candidate_id, repo)`. A companion case confirms a manifest package that *does* match an existing Detection Pattern produces no Sighting.

The batch job gets one new, dedicated seam — `taxonomy_growth.publish_new_skill_tags()` called directly (no HTTP surface exists for it), with `FakeRegistryClient` and `FakeGroqClient` injected, following the same DB-session-fixture pattern as `db_session_factory` in `tests/conftest.py`. Scenarios: (a) below-threshold Sightings produce no publish; (b) at-threshold Sightings where the registry confirms existence and the LLM drafts a tag → taxonomy gains the entry, `version` bumps once, the new entry's `manifest_packages` matches the Sighting exactly; (c) registry says the package doesn't exist → skipped, no LLM call made (assert on `FakeGroqClient.calls`); (d) exact-name duplicate of an existing entry → skipped before the LLM is called; (e) LLM abstains (`draft_skill_tag` returns `None`) → no entry added; (f) a pair already marked decided in an earlier run → not reprocessed on a later run even with fresh Sightings added; (g) two eligible pairs published within one run → `version` bumps exactly once, not twice.

## Out of Scope

- **Human approval / Admin review UI** — deliberately dropped (ADR-0008); no Admin actor or auth is introduced anywhere in this pass.
- **Retraction/undo tooling** for a bad auto-published entry — corrected via the same manual `skills.json` edit already used for hand-curated fixes.
- **New ecosystem support** beyond whatever the current taxonomy's `manifest_packages` entries already reference.
- **Sighting exposure to Candidates or Recruiters** — Sightings are internal-only bookkeeping, never part of any API response.
- **Per-tag `taxonomy_version`** — the global-counter fork mechanics from ADR-0005 are unchanged; this spec only adds a publish cadence to bound how often it bumps, not a redesign of what it bumps.
- **Scheduling mechanism itself** (which cron/scheduler, exact cadence) — deployment configuration, not application code.
- **Depth Interview** and **multi-platform evidence sourcing** — unrelated deferred features, unaffected by this spec.

## Further Notes

Full design history lives in `CONTEXT.md` (round 8) and `docs/adr/0008-self-extending-taxonomy-skips-human-review.md` — worth reading alongside this spec for the "why" behind dropping human review in favor of the deterministic-check-plus-LLM-abstain guard combination. This spec extends `.scratch/skillproof-mvp/spec.md` issue 02 (taxonomy) and `.scratch/skillproof-hybrid-scoring/spec.md` issue 01 (Detection Patterns) rather than replacing either — every Skill Tag this feature publishes must still satisfy the "authorable Detection Pattern" scoping rule established there.
