# Span Ceiling caps confidence score for short, unsustained bursts of activity

Span's existing 15% weight rewards a longer qualifying-evidence date range, but only as one slice of an additive sum — a Candidate with a short, intense burst of Volume and Depth evidence can still reach a high Confidence Score, discounted by no more than Span's 15% share. We decided to add a Span Ceiling: a separate multiplicative factor applied to the final Confidence Score, using its own saturation curve and a saturation constant larger than Span's own `SPAN_SATURATION_DAYS`, so that "earning some Span credit" and "not being ceiling-capped" remain two distinct bars rather than collapsing into the same threshold.

## Consequences

The Span Ceiling is not a fifth Signal — it sits outside the four-Signal weighted sum (Presence/Volume/Depth/Span still combine exactly as ADR-0004 specifies) and is applied as a final multiplication on the resulting Confidence Score. This keeps ADR-0004's fixed weights untouched, avoiding reopening a decision that document explicitly defers until real outcome data exists. The Ceiling deliberately uses a smooth saturating curve, matching every other constant in the scoring formula (Volume, Span, and Depth's self-authored discount are all continuous functions, not step functions) rather than a hard numeric cutoff, so there's no arbitrary cliff edge between two Candidates a day apart in sustained activity. The exact saturation constant is left as an informed prior, calibrated later, consistent with every other constant `scoring.py` already documents as such.

## Considered Options

Replacing Span's existing weighted-sum slot with the ceiling function directly — rejected: conflates two different jobs (Span's weight rewards *having* a long history; the Ceiling penalizes *not* having one) and would have reopened the already-settled 0.20/0.40/0.25/0.15 weighting, which ADR-0004 explicitly defers.

A hard cutoff (e.g. "score capped at X below N days"), mirroring gitfut's literal "caps at 88" language — rejected in favor of a smooth curve, for consistency with the rest of the formula's style and to avoid a discontinuous boundary.
