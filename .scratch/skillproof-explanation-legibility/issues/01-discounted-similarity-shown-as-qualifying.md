# 01 — Explanations cite a discounted similarity that can read as sub-floor

**What to build:** Not yet decided — see the Open Questions in `../spec.md`. This ticket needs a scoping/grilling pass to pick between showing the raw qualifying similarity, showing both numbers, or relabeling the existing one, before an agent can implement it.

**Blocked by:** None — but not ready for implementation until scoped (see Status).

**Status:** needs-triage

- [ ] Decide what `EvidenceRefOut.similarity` (and `explain_service.build_prompt`'s evidence lines) should show for a self-authored (commit-message) item: the raw qualifying similarity, the Depth-ranking (discounted) value, or both under distinct names.
- [ ] Decide whether the Explanation prompt should be told a shown similarity may be discounted, so the LLM doesn't characterize a post-discount number ("moderate," "low," etc.) as if it were the raw qualifying similarity.
- [ ] Confirm the fix doesn't change `similarity`'s meaning for any other existing consumer of `EvidenceRefOut` (the public Evidence Card page's commit list, `/search`'s per-skill breakdown per ADR-0007).
- [ ] Once scoped, add regression coverage: a self-authored item with raw similarity comfortably above 0.35 whose discounted value falls below 0.35 should not produce an Explanation (or an API response) that reads as contradicting the documented qualifying floor.

## Comments

Opened from a live example: a `verified` React Evidence Card's Explanation cited "moderate similarity of 0.2614" for a commit that actually qualified on a raw similarity around 0.44 — the 0.2614 is `raw_similarity * DEPTH_COMMIT_MESSAGE_DISCOUNT` (0.6, `scoring.py:86-90`) for a self-authored commit-message match, not the qualifying similarity itself. See `../spec.md` for the full root-cause writeup.
