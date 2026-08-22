# 02 — Hybrid Presence/Volume/Depth/Span scoring (core formula)

**What to build:** `/verify` computes each claimed Skill Tag's Confidence Score from four Signals — Presence, Volume, Depth, Span — instead of a single embedding-similarity average, replacing the MVP's pure-embedding scoring with the formula recorded in ADR-0004.

**Blocked by:** 01 (needs Detection Patterns to compute Presence and Volume against)

**Status:** done

- [x] Confidence Score is computed as `0.20×presence + 0.40×volume + 0.25×depth + 0.15×span`, each Signal bounded [0,1].
- [x] Presence is a deterministic manifest/file-extension lookup against the Skill Tag's Detection Pattern — no embedding model involved.
- [x] Volume is `n_commits / (n_commits + 5)`, where `n_commits` is the count of the Candidate's own commits touching files matching the Detection Pattern. External-repo commits still use the existing author-filtered fetch at this point — PR-scoping is a later ticket.
- [x] Depth is `mean(top_3(cosine_sims))` — the three highest-similarity Volume-qualifying items (each still subject to the existing 0.35 qualifying floor) compared against the Skill Tag's canonical description.
- [x] Span is `span_days / (span_days + 90)`, measured over the full qualifying evidence set, replacing the MVP's linear-with-floor multiplier.
- [x] `evidence_type` is `"none"` when Presence = 0 and Volume = 0, `"declared_only"` when Presence = 1 and Volume = 0, and `"verified"` when Volume > 0.
- [x] A Skill Tag declared in a manifest but never touched by any qualifying commit produces `evidence_type = "declared_only"` and a small nonzero Presence-only Confidence Score, rather than `confidence_score = 0`.
- [x] `GitHubClient` gains a method to fetch a repo's manifest files (the well-known set — `package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, `pom.xml`, etc. — missing files ignored), fetched once per repo, not once per claimed skill.
- [x] The existing docs/config-only commit filter does not drop a file that is itself a registered Detection Pattern for some Skill Tag (e.g. `Dockerfile` for the Docker Skill Tag).
- [x] `GET /search` results include `evidence_type` per result.
