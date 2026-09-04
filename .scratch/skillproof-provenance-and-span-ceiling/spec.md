# SkillProof — Provenance Check and Span Ceiling

Status: ready-for-agent

## Problem Statement

ADR-0004's hybrid scoring formula closes two specific gaming surfaces — forking a large repo to inflate Volume, and writing an elaborate commit message to inflate Depth — but a third stayed open, and a related scoring-shape gap sat alongside it. First: for a Candidate's own, non-forked repo, Volume already trusts `author = candidate` at face value with no check on whether that history was actually authored by them versus imported or relabeled from elsewhere — a Candidate could import another project's real git history into a fresh repo and claim its commits as their own work. Second: Span's existing 15% additive weight means a short, intense burst of otherwise-strong Volume and Depth evidence can still reach a high Confidence Score, discounted by no more than that 15% share — there's nothing that specifically penalizes a lack of sustained activity the way a longer history is rewarded.

Both gaps, and the two mechanisms that close them, were surfaced by reviewing five open-source GitHub-analysis repos (gitfut, gh-fake-analyzer, GitHub-Profile-Analyzer, ossinsight, gitinspector) for reusable scoring logic — not to copy their code, but to stress-test SkillProof's own formula against ideas those projects had already worked through. See CONTEXT.md round 11, ADR-0012, and ADR-0013 for the full design history.

## Solution

**Provenance Check.** For each owned, non-forked repo already present in the current Evidence Bundle, one GitHub commit-search API call checks whether that repo's earliest commit's SHA already exists in another public repo the Candidate doesn't own. A match hard-disqualifies that repo's commits from Volume, Depth, and Span for this Candidate — Presence is unaffected, since a manifest declaration isn't an authorship claim. The check runs silently: it changes the resulting Confidence Score but is never surfaced as a visible label on the Evidence Card. A positive match is cached permanently; a clean result is re-checked on every future `/verify` call.

**Span Ceiling.** A new multiplicative factor, applied to the final Confidence Score after the existing four-Signal weighted sum, using its own smooth saturation curve and a saturation constant distinct from (and larger than) Span's own `SPAN_SATURATION_DAYS`. It does not replace or touch Span's existing 0.15 weight or ADR-0004's fixed weights — it's a separate final adjustment, not a fifth Signal.

## User Stories

**Candidate — trust and integrity**

1. As a Candidate, I want my score to only reflect commits I actually authored myself, not history imported from a project I don't own, so a verified Evidence Card means the same thing for every Candidate.
2. As a Candidate, I want a Provenance Check match to lower my score quietly rather than publish a visible accusation on my public Evidence Card, so an automated heuristic (even a high-precision one) can't publicly brand me without a dispute process that doesn't exist yet.
3. As a Candidate, I want importing my own already-merged, PR-based contribution to an external project into a personal showcase repo to cost me nothing, since that contribution already counts through the existing external-repo path — the Provenance Check should only ever prevent double-counting, never reduce real credit I'd otherwise have.
4. As a Candidate, I want sustained activity on a skill over time to matter for reaching a high score, not just for earning Span's own 15% share, so a short lucky burst can't fully substitute for real, ongoing experience.

**Recruiter**

5. As a Recruiter, I want a Candidate's Confidence Score to already reflect these integrity checks, so I don't need to independently audit whether evidence behind a high score is genuinely the Candidate's own sustained work.

**Platform**

6. As the SkillProof system, I want the Provenance Check to run at most once per owned repo per `/verify` call (not once per commit), so the added GitHub API cost stays bounded and compatible with `/verify`'s existing in-process, no-queue execution model.
7. As the SkillProof system, I want a positive Provenance Check match cached permanently and a clean result re-checked on future re-verifications, so the check doesn't waste API calls re-confirming an already-established match, but also doesn't treat a clean result today as a permanent guarantee.
8. As the SkillProof system, I want the Span Ceiling implemented as a separate, clearly-named final multiplication — not folded into the existing four-Signal weighted sum — so ADR-0004's fixed weights stay untouched and the two mechanisms' distinct jobs (rewarding sustained span vs. penalizing its absence) stay legible in the code.

## Implementation Decisions

**Provenance Check scope.** Runs only against owned, non-forked repos already present in the current Evidence Bundle for the skills being verified — never a full-account scan of every repo the Candidate owns, and never applied to external (non-owned) repos, which are already covered by ADR-0004's PR-membership check.

**Detection mechanism.** For each in-scope repo, fetch its earliest commit and query GitHub's commit-search API for that SHA, scoped to exclude repos owned by the Candidate. Any match is sufficient — no corroboration across multiple commits required, since a SHA match is already high-precision.

**Consequence of a match.** The repo's commits are excluded entirely from that skill's `matching_items` before Volume, Depth, and Span are computed — equivalent to the repo never having been ingested for those three Signals. Presence (manifest-based) is computed independently and is unaffected.

**Caching.** A positive match is persisted per-repo and treated as permanent. A repo with no match is not cached as "clear" — it's re-checked on the next `/verify` that includes it.

**Transparency.** No new `evidence_type` value, no new field on `EvidenceCardOut`, no Candidate- or Recruiter-facing indication that a Provenance Check exclusion occurred. The only observable effect is a lower Confidence Score (or, if all of a skill's evidence came from the disqualified repo, the same "none"/"declared_only" outcome as if that evidence never existed).

**Span Ceiling formula.** A new named constant (e.g. `SPAN_CEILING_SATURATION_DAYS`, distinct from and larger than `SPAN_SATURATION_DAYS`) drives a saturating multiplier applied to `confidence_score` after the existing weighted sum and clamping. Exact constant value is an informed prior, calibrated later — consistent with every other constant already documented that way in `scoring.py`.

**Ordering.** The Provenance Check runs as its own step in `verify_service.py`, right after `ingest_evidence` returns and before scoring — the same shape as the existing `sightings.record_sightings` call, not woven into `ingestion.py` itself. The Span Ceiling multiplication happens inside `score_skill`, after the existing four-Signal weighted sum and its `[0,1]` clamp, as a final step.

## Testing Decisions

Same seam as the existing scoring suite (`tests/test_scoring.py`, `FakeGitHubClient`): both mechanisms are pure deterministic code over fixture data, run for real, never mocked.

New fixture scenarios needed: an owned repo whose earliest commit SHA is fabricated to match a fixture "external" repo not owned by the candidate, proving Provenance Check excludes its commits from Volume/Depth/Span while leaving Presence (from that same repo's manifest) unaffected; a repeat `/verify` over an already-flagged repo, proving the cached match persists without a second API call; a repeat `/verify` over a clean repo, proving it's re-checked rather than cached; a short-span, high-Volume/Depth fixture and a long-span, equivalent-Volume/Depth fixture, proving the Span Ceiling produces a materially different final score between the two even though the pre-Ceiling weighted sum is identical.

## Out of Scope

- **Full cross-repo hash comparison across every commit**, not just a repo's earliest one — deferred as a follow-up once the cheap, single-commit check has proven the concept in practice (ADR-0012).
- **A visible provenance flag or dispute/appeal mechanism** on the Evidence Card — a separate, weightier product decision (public accusation with no due process) deferred to its own future grilling session.
- **Folding PR/review counts into Volume as additional diminishing-returns inputs** (considered against gitfut's multi-type formula, rejected — see CONTEXT.md round 11) — not part of this spec.
- **Recalibrating the Span Ceiling's saturation constant against real outcome data** — same "informed prior, fit later" status as every other constant in the formula.

## Further Notes

Full design history and rationale live in `CONTEXT.md` round 11 and two ADRs: `docs/adr/0012-provenance-check-disqualifies-imported-history.md` and `docs/adr/0013-span-ceiling-caps-unsustained-bursts.md` — worth reading alongside this spec for the "why" behind each decision above, including the rejected alternatives (a commit-date heuristic for provenance, a hard cutoff for the ceiling) and the reasoning for why each was rejected.
