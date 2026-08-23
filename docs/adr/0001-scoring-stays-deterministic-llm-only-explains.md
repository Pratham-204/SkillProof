# Scoring stays deterministic and LLM-free; the LLM only writes explanations

The Confidence Score must stay reproducible and free to compute, but a bare number like `0.87` isn't legible to a recruiter comparing candidates. We decided the score itself is computed entirely by local sentence-transformer embeddings (cosine similarity of qualifying Evidence Items, times a temporal multiplier) and is never touched by an LLM. A separate, optional Explanation layer calls Groq (Llama 3.3 70B, free tier) once per viewed skill to turn the same evidence into a one-sentence human-readable justification, with a deterministic template sentence as fallback if the call fails or the free tier is rate-limited.

## Consequences

If scoring ever needs LLM-grade reasoning (e.g. judging code quality, not just topical similarity), that is a new architectural decision, not an extension of the explanation call — the explanation LLM has no path to influence the numeric score.
