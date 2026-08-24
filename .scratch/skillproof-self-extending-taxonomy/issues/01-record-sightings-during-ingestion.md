# 01 — Record Sightings during ingestion

**What to build:** `/verify`'s existing manifest-fetching step also records a Sighting whenever a Candidate's manifest declares a package matching no existing Skill Tag's Detection Pattern.

**Blocked by:** None — can start immediately

**Status:** done

- [x] A new `Sighting` record (ecosystem, package name, candidate, repo, seen-at) is persisted for every manifest-declared package that matches no existing Skill Tag's Detection Pattern, covering the ecosystems the taxonomy's `manifest_packages` entries already reference (npm, pip, gem, composer, hex, pub, maven).
- [x] Sighting recording adds no LLM call and no extra fetch/parse work beyond what ingestion already does — it runs over manifest content already fetched once per repo.
- [x] A manifest package that already matches an existing Skill Tag's Detection Pattern produces no Sighting.
- [x] Re-verifying the same candidate against the same repo/package does not create a duplicate Sighting row.
- [x] Sightings are internal bookkeeping only — not exposed through any API response.

## Comments

Implemented via a new `manifest_parsing.py` (per-ecosystem parsers for `package.json`, `requirements.txt`/`pyproject.toml`/`Pipfile`, `Gemfile`, `composer.json`, `mix.exs`, `pubspec.yaml`, `pom.xml`), a new `sightings.py` (`record_sightings`, diffing against `taxonomy.known_manifest_package_names()`), a new `Sighting` model with a `(ecosystem, package_name, candidate_id, repo)` unique constraint, and one new call site in `verify_service.run_verification` right after ingestion succeeds. Tests: `tests/test_manifest_parsing.py` (pure parser unit tests) and two new cases in `tests/test_api_flow.py` at the existing HTTP seam.
