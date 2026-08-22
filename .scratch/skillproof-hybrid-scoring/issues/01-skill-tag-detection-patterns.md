# 01 — Skill Tag taxonomy: Detection Patterns + code-detectable-only scope

**What to build:** The taxonomy shrinks to skills that can actually be detected from GitHub activity, and every surviving Skill Tag carries an authored Detection Pattern that later tickets will use to compute Presence and Volume.

**Blocked by:** None — can start immediately

**Status:** done

- [x] Every Skill Tag remaining in the taxonomy carries an authored Detection Pattern — package identifier(s), import pattern(s), API surface marker(s), config filename(s), or (for language Skill Tags) file extension(s)/ecosystem-manifest marker — alongside the existing canonical description used for the Depth Signal.
- [x] Skill Tags with no authorable Detection Pattern (System design, Security engineering, Accessibility, Performance optimization, Event-driven architecture, Microservices architecture, and similar practice/theoretical skills) are removed from the taxonomy.
- [x] A claim against a removed Skill Tag is rejected by the existing unknown-Skill-Tag check in `/verify` — no new rejection code path is required, just correct data.
- [x] `GET /skills` continues to serve the (now trimmed) taxonomy for autocomplete, unchanged in response shape.
- [x] The taxonomy is stamped with a version identifier that a later ticket (taxonomy versioning) will read and compare against.
