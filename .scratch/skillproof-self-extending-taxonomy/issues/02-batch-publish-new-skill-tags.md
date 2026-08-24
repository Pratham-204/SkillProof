# 02 — Batch job publishes new Skill Tags from accumulated Sightings

**What to build:** A callable batch entry point that turns enough accumulated Sightings for a package into an actual, claimable Skill Tag — confirming the package exists on its real ecosystem registry, rejecting exact and LLM-judged semantic duplicates, letting the LLM draft a category+description or abstain, and publishing with a single `taxonomy_version` bump.

**Blocked by:** 01 (needs real Sighting records to operate on)

**Status:** done

- [x] A (ecosystem, package_name) pair becomes eligible once it has Sightings from at least N distinct candidates (N a named constant).
- [x] For each eligible pair, in order: skip if already decided; skip if the package doesn't exist on its ecosystem's real registry (`RegistryClient`); skip if it's an exact/case-insensitive name duplicate of an existing Skill Tag; otherwise ask the LLM (`GroqClient.draft_skill_tag`) to draft a category + canonical description or abstain, checking semantic duplication against every existing Skill Tag's description.
- [x] The LLM's category choice is constrained to the taxonomy's existing five categories — a response outside that set is treated as an abstain.
- [x] A published Skill Tag's Detection Pattern is populated directly from the Sighting (`manifest_packages = [{ecosystem, package_name}]`) — the LLM never authors it.
- [x] `taxonomy_version` bumps exactly once per batch run that publishes at least one new Skill Tag, never once per tag.
- [x] A pair already decided (published, rejected-duplicate, or abstained) in an earlier run is never re-evaluated by a later run, even if freshly sighted again.
- [x] A published Skill Tag is usable by every existing code path (`/verify`, `/skills`, `/search`, scoring) with no special-casing — including getting a real embedding via the existing self-healing embeddings cache.
- [x] A scriptable entry point exists that a scheduler can invoke non-interactively to run the batch job against the real DB and real clients.

## Comments

Implemented via `registry_client.py` (`RegistryClient`/`RealRegistryClient`/`FakeRegistryClient`), `GroqClient.draft_skill_tag` + `SkillTagDraft` in `groq_client.py`, a new `SightingDecision` model, `taxonomy.append_skill_tags`/`taxonomy.CATEGORIES`, the core `taxonomy_growth.publish_new_skill_tags`, and `taxonomy_growth_cli.py` as the scheduler entry point. Tests: `tests/test_taxonomy_growth.py`, covering all scenarios from the spec's Testing Decisions plus an invalid-category and an LLM-failure case, using a new `isolated_taxonomy_file` fixture so tests never mutate the checked-in `skills.json`.

