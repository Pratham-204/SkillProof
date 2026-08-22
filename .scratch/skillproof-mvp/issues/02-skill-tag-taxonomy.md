# 02 — Skill Tag taxonomy

**What to build:** A fixed, hand-curated taxonomy of technical skills that Candidates claim against, with embeddings precomputed once and cached — no free-text claims.

**Blocked by:** None — can start immediately, independent of 01.

**Status:** done

- [x] A static, hand-curated list of roughly 100-150 Skill Tags (languages, frameworks, datastores, infra/tools) is checked into the repo.
- [x] Each Skill Tag's embedding is computed once locally (sentence-transformers) and cached rather than recomputed per request.
- [x] A listing/lookup exists so a client can build an autocomplete UI against the taxonomy.
- [x] A claim referencing a Skill Tag not in the taxonomy is rejected rather than silently accepted as free text.

## Comments

Substantially rewritten by `.scratch/skillproof-hybrid-scoring/issues/01-skill-tag-detection-patterns.md` — the taxonomy now scopes to code-detectable Skill Tags carrying a Detection Pattern, dropping practice/theoretical skills with no code footprint. That ticket is the current source of truth for the taxonomy's shape.
