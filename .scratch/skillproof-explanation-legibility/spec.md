# Explanation Text Cites a Discounted Similarity, Not the Qualifying One

Status: needs-triage

## Problem Statement

An Explanation generated for a `verified` Evidence Card can describe a source commit's similarity using a number that reads as *below* the product's own stated 0.35 qualifying floor (the Evidence Item term in `CONTEXT.md`), even though the item legitimately cleared that floor. This isn't a hallucination — the LLM is accurately restating a number it was handed — but the number itself is misleading out of context, which undermines the Explanation's whole purpose: being a legible, trustworthy justification for the Confidence Score.

Concretely, one live Explanation read: "...supported by a single verified commit ... which exhibits a moderate similarity of 0.2614 to React-related patterns." 0.2614 is below the documented 0.35 floor. A Candidate or Recruiter who has read the Evidence Item term would reasonably wonder why this counts as evidence at all.

## Root Cause

`scoring.py`'s `score_skill` qualifies an item using its **raw** cosine similarity (`scoring.py:84`, `if raw_similarity < settings.evidence_qualifying_floor: continue`). But the value actually stored on `source_commits` / returned as `EvidenceRefOut.similarity` — and the value `explain_service.build_prompt` interpolates into the LLM prompt's evidence lines — is the **Depth-ranking value** (`scoring.py:86-90`): `raw_similarity * DEPTH_COMMIT_MESSAGE_DISCOUNT` (0.6) whenever `item.is_self_authored` (i.e., the match came from a commit message rather than a PR review comment — the round-6 / ADR-0004 discount, applied because a commit message is Candidate-authored and easier to game than a PR comment).

So a self-authored item with raw similarity ~0.44 (comfortably above the 0.35 floor) can display as 0.2614 after the discount, with nothing in the API response or the prompt indicating that the number shown is a post-discount ranking score rather than the qualifying similarity.

PR-comment-sourced items are never discounted (`is_self_authored` is false for them), so this specifically only affects commit-message-derived evidence — which, per round 9, is every piece of Depth evidence for `language`-category Skill Tags (PR comments are deliberately never Depth evidence there), making this the common case for skills like Python/JavaScript/React, not an edge case.

## Open Questions

- Should `EvidenceRefOut.similarity` (and the prompt's evidence lines) show the raw qualifying similarity instead of the Depth-ranking value, show both, or keep just the ranking value but relabel it clearly?
- If both numbers are surfaced, how should the schema name them so `similarity` doesn't silently change meaning for existing consumers (the public Evidence Card page, `/search`)?
- Should the Explanation prompt itself be told explicitly that a shown similarity may be discounted for self-authored items, so the LLM can phrase around it (e.g., not calling a discounted number "moderate" or "low" at face value)?

## Out of Scope

- The ×0.6 discount itself (round 6, ADR-0004) — that weighting decision stands; this is only about how the resulting number is surfaced and described.
- `template_fallback`'s wording — it never cites a per-item similarity number, only aggregate counts (commits/repos/days), so it isn't affected by this.

## Further Notes

Surfaced while fixing the Groq model deprecation that had `/explain` stuck on template fallback (see `groq_client.py`'s `_post_chat` and `Settings.groq_model`) — this is a separate, pre-existing issue in the Explanation content itself, not part of that fix.
