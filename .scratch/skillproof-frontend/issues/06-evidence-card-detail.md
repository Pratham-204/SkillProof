# 06 — Evidence Card detail + lazy explanation

**What to build:** The expanded view of a single Evidence Card — source commits/PR comments, and a plain-English Explanation fetched only on interaction, not during the reveal.

**Blocked by:** 02, 05.

**Status:** done

- [x] Expanding a card (from the reveal or from a static list) shows its `source_commits`/`source_comments` list (`EvidenceRefOut`), each linking out to the real commit/PR comment URL.
- [x] The Explanation is not fetched when the card first reveals. It's fetched via `POST /explain/{candidate_id}/{skill}` only when the user expands/interacts with that specific card, and shown with a loading state while the call is in flight.
- [x] Once fetched, the Explanation is cached client-side for the session so re-expanding the same card doesn't re-fetch (the backend already caches server-side on the Evidence Card; this avoids a redundant round-trip on top of that).
- [x] `explanation_is_fallback: true` is surfaced distinctly (however subtly) from an LLM-generated explanation — it's a real, meaningful state per the backend's design (template fallback vs. real LLM output), not noise to hide.
- [x] A Candidate with `needs_reconnect: true` sees a reconnect prompt (link to `/auth/github/login`) somewhere reachable from this view, not just buried on the claim screen.

## Comments

**Implementation:** `EvidenceCardTile` (used by ticket 05's `ScanReveal`) gained its own expand/collapse state (`expanded`) plus explanation state (`explanation`/`isFallback`/`explaining`/`explainError`), seeded from whatever the card already carries (`card.explanation`/`card.explanation_is_fallback` — nonzero if a previous verification run already cached one server-side) so a truly-cached explanation never triggers a fetch at all. Clicking the card header (now a `<button>`) toggles `expanded`; opening it for the first time (`explanation === null`) calls `explainSkill(candidateId, card.skill)` once and holds the result in this component's own state for as long as the tile stays mounted — satisfying "cached for the session" without a separate cache layer, since the tile isn't remounted between expand/collapse. `source_commits` render as a list of links (`ref.kind === 'commit' ? 'commit' : 'PR comment'`, truncated ref, repo name, `target="_blank"` to the real GitHub URL). `explanation_is_fallback` shows a small "template fallback" pill next to the explanation text rather than hiding the distinction.

`candidateId` had to be threaded into `EvidenceCardTile` as a new required prop (`ScanReveal.tsx` now tracks the full `Candidate` object from `getMe()`, not just its id, so it has `needs_reconnect` available too). The reconnect prompt lives in `ScanReveal`'s `complete` phase (an amber banner above the card list, linking to `GITHUB_LOGIN_URL`) rather than inside the tile itself, since the tile is a dumb, reusable component ticket 07's public page will also render for other people's cards, where `needs_reconnect` doesn't apply to the viewer at all.

**Verified via:** `tsc -b` (clean) and `vite build` (435 modules, clean) — same Chrome-browser-tools gap disclosed in tickets 04/05 applies here too (no interactive click-through this session).

**Gap closed:** click-tested live (see ticket 05's update) — expanding the Python card showed its lazily-fetched Explanation with a "template fallback" pill, confirming the expand-to-fetch, cache-on-reexpand, and `explanation_is_fallback` surfacing all work as designed. This live run also surfaced and led to fixing a real bug in the fallback text itself — see `explain_service.py`'s `template_fallback` fix noted in ticket 05.
