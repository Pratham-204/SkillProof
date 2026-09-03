# 01 — Explanations cite a discounted similarity that can read as sub-floor

**What to build:** `source_commits`/`EvidenceRefOut.similarity` (and the Explanation prompt fed by it) should show the raw similarity that actually cleared the 0.35 qualifying floor, not the ×0.6-discounted Depth-ranking value, so it can never read as contradicting the documented floor.

**Blocked by:** None.

**Status:** done

- [x] `EvidenceRefOut.similarity` shows the raw qualifying similarity for a self-authored (commit-message) item, not the Depth-ranking (discounted) value — resolved by switching `scoring.py:110` to store each item's `raw_similarity` rather than its `depth_similarity`.
- [x] The Explanation prompt doesn't need to be told a shown similarity may be discounted — moot once the displayed value is always the raw, floor-clearing similarity.
- [x] Confirmed the fix doesn't change `similarity`'s meaning for any other consumer: checked the frontend (only types the field, never renders it), `/search` (ranks by `average_score`, unrelated), and Depth's own score computation (already independent of what's stored in `source_commits`).
- [x] Regression coverage added/updated in `test_scoring.py`: a self-authored item with raw similarity above 0.35 whose discounted value would fall below 0.35 now displays its raw similarity in `source_commits`, while `confidence_score` still reflects the discount (pinned exactly in `test_fake_backend_pins_the_exact_discount_on_commit_message_depth`).

## Comments

Opened from a live example: a `verified` React Evidence Card's Explanation cited "moderate similarity of 0.2614" for a commit that actually qualified on a raw similarity around 0.44 — the 0.2614 is `raw_similarity * DEPTH_COMMIT_MESSAGE_DISCOUNT` (0.6, `scoring.py`) for a self-authored commit-message match, not the qualifying similarity itself.

Triaged as `bug` (an existing documented invariant — CONTEXT.md's Evidence Item term — was being visibly violated in what the app actually shows, not a missing feature). Verified the exact root cause against the live example before scoping: confirmed the React card's item was `kind: "commit"` (always `is_self_authored`), and that `raw ≈ 0.2614 / 0.6 ≈ 0.4357`, well above the floor.

Resolved directly in this session rather than handed off — see `../spec.md` for the full solution and implementation/testing decisions.
