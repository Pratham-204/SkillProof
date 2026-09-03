# Explanation Text Cites a Discounted Similarity, Not the Qualifying One

Status: done

## Problem Statement

An Explanation generated for a `verified` Evidence Card can describe a source commit's similarity using a number that reads as *below* the product's own stated 0.35 qualifying floor (the Evidence Item term in `CONTEXT.md`), even though the item legitimately cleared that floor. This isn't a hallucination — the LLM is accurately restating a number it was handed — but the number itself is misleading out of context, which undermines the Explanation's whole purpose: being a legible, trustworthy justification for the Confidence Score.

Concretely, one live Explanation read: "...supported by a single verified commit ... which exhibits a moderate similarity of 0.2614 to React-related patterns." 0.2614 is below the documented 0.35 floor. A Candidate or Recruiter who has read the Evidence Item term would reasonably wonder why this counts as evidence at all.

## Root Cause

`scoring.py`'s `score_skill` qualifies an item using its **raw** cosine similarity (`scoring.py:84`, `if raw_similarity < settings.evidence_qualifying_floor: continue`). But the value actually stored on `source_commits` / returned as `EvidenceRefOut.similarity` — and the value `explain_service.build_prompt` interpolates into the LLM prompt's evidence lines — was the **Depth-ranking value**: `raw_similarity * DEPTH_COMMIT_MESSAGE_DISCOUNT` (0.6) whenever `item.is_self_authored` (i.e., the match came from a commit message rather than a PR review comment — the round-6 / ADR-0004 discount, applied because a commit message is Candidate-authored and easier to game than a PR comment).

So a self-authored item with raw similarity ~0.44 (comfortably above the 0.35 floor) could display as 0.2614 after the discount, with nothing in the API response or the prompt indicating the number shown was a post-discount ranking score rather than the qualifying similarity.

PR-comment-sourced items are never discounted (`is_self_authored` is false for them), so this specifically only affected commit-message-derived evidence — which, per round 9, is every piece of Depth evidence for `language`-category Skill Tags (PR comments are deliberately never Depth evidence there), making this the common case for skills like Python/JavaScript/React, not an edge case.

## Solution

`QualifyingEvidence.similarity` / `EvidenceRefOut.similarity` (and therefore the Explanation prompt's evidence lines) now always shows the raw similarity that actually cleared the 0.35 qualifying floor. The ×0.6 discount stays exactly where it was doing real work — Depth's top-3 ranking and averaging — it's just no longer also used as the displayed number.

Checked the blast radius before deciding this was safe: `similarity` has exactly one downstream consumer, `explain_service.build_prompt`. The frontend only types the field (`api.ts`) and never renders it; `/search`'s ranking uses `average_score` (ADR-0007), unrelated; and Depth's own score computation was already independent of what gets stored in `source_commits` — so switching the displayed value to raw similarity changes nothing else.

## Implementation Decisions

- `scoring.py`'s internal `qualifying` list now carries `(item, raw_similarity, depth_similarity)` per item instead of `(item, depth_similarity)` — ranking/`top_n` selection and Depth's average still sort and average on `depth_similarity` (discounted), but `source_commits` is built from each item's `raw_similarity` instead.
- No schema change: `QualifyingEvidence`/`EvidenceRefOut.similarity` keeps its existing name and type — it's now simply correct (the raw qualifying similarity) rather than a second, unlabeled field being needed. No API consumer depended on the discounted value (see blast-radius check above), so no versioning or migration concern.
- No prompt change needed: once `similarity` is always the raw qualifying value, it can never read as sub-floor, so the earlier open question about telling the LLM "this may be discounted" became moot.

## Testing Decisions

Three existing `test_scoring.py` tests had encoded the old (buggy) discounted-display behavior as the expected behavior and needed rewriting, not just new coverage:

- `test_depth_discounts_commit_message_similarity_relative_to_pr_comment` → renamed `test_source_commits_similarity_is_undiscounted_even_for_a_commit_message_match`; now asserts a commit-message match and a PR-comment match with identical text show *equal* `source_commits[].similarity` (proving the fix), rather than asserting the commit's displayed value was lower.
- `test_fake_backend_precisely_includes_similarity_just_above_the_qualifying_floor` — now asserts `source_commits[0].similarity == 0.36` (the raw value) instead of the discounted `0.36 * 0.6`.
- `test_fake_backend_pins_the_exact_discount_on_commit_message_depth` — now asserts *both* that `source_commits` shows `1.0` (raw, undiscounted) for both items, *and* that `confidence_score` still reflects the discount via a hand-computed expected value (`depth = mean(1.0 * 0.6, 1.0) = 0.8`), so the discount's effect on the actual score stays covered even though it's no longer provable through `source_commits.similarity`.

## Out of Scope

- The ×0.6 discount itself (round 6, ADR-0004) — that weighting decision stands; this was only about how the resulting number is surfaced and described.
- `template_fallback`'s wording — it never cites a per-item similarity number, only aggregate counts (commits/repos/days), so it wasn't affected by this.

## Further Notes

Surfaced while fixing the Groq model deprecation that had `/explain` stuck on template fallback (see `groq_client.py`'s `_post_chat` and `Settings.groq_model`) — a separate, pre-existing issue in the Explanation content itself, unrelated to that fix.
