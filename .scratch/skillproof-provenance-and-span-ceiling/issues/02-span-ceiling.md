# 02 — Span Ceiling: cap confidence score for unsustained bursts

**What to build:** Close the scoring-shape gap where a short, intense burst of Volume/Depth evidence can reach a high Confidence Score discounted by no more than Span's 15% weight. Add a Span Ceiling: a separate multiplicative factor on the final Confidence Score, distinct from and layered on top of the existing four-Signal weighted sum.

**Blocked by:** none (applies to `scoring.py`'s existing `score_skill`, independent of issue 01)

**Status:** ready-for-agent

- [ ] Add a new named constant for the Ceiling's saturation curve (e.g. `SPAN_CEILING_SATURATION_DAYS`), distinct from and larger than `SPAN_SATURATION_DAYS` — do not reuse or rename the existing constant.
- [ ] After the existing `confidence_score = PRESENCE_WEIGHT * presence + VOLUME_WEIGHT * volume + DEPTH_WEIGHT * depth + SPAN_WEIGHT * span` computation and its `[0,1]` clamp, apply a smooth saturating multiplier derived from `span_days` and the new constant (mirroring the shape of the existing `n/(n+k)` saturation curves already used for Volume and Span — not a hard cutoff/step function).
- [ ] `PRESENCE_WEIGHT`, `VOLUME_WEIGHT`, `DEPTH_WEIGHT`, `SPAN_WEIGHT`, and their 0.20/0.40/0.25/0.15 values (ADR-0004) are unchanged by this work — the Ceiling is a final adjustment, not a fifth Signal, and does not touch the weighted-sum formula itself.
- [ ] A fixture demonstrates the effect: two fixtures with identical Presence/Volume/Depth inputs but different `span_days` (one short-burst, one long-sustained) produce different final `confidence_score` values despite an identical pre-Ceiling weighted sum.
- [ ] A fixture demonstrates the floor case: a Candidate with zero qualifying evidence (`span_days = 0`) still produces `confidence_score = 0`, not a divide-by-zero or other edge-case failure in the Ceiling's saturation formula.

## Comments
