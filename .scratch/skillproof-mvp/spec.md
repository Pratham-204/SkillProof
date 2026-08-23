# SkillProof MVP

Status: ready-for-agent

## Problem Statement

Developer skill profiles are self-reported text — a resume line or a LinkedIn tag — and recruiters have no way to check whether a Candidate has actually used a claimed technology in production without an expensive screening call. Candidates, in turn, have no way to prove a claim beyond listing it.

## Solution

A Candidate connects their GitHub account and selects the skills they want verified from a fixed taxonomy. SkillProof cross-references their public commit and PR history against each claimed Skill Tag and produces a public Evidence Card per skill: a Confidence Score, the specific commits/PR comments that produced it, and a plain-English Explanation. Candidates can optionally opt in to being discoverable, letting Recruiters search verified candidates by skill and minimum confidence — without either side needing an account.

## User Stories

**Candidate — connecting and claiming**

1. As a Candidate, I want to connect my GitHub account via OAuth, so that SkillProof can read my public activity without me manually uploading anything.
2. As a Candidate, I want to select the skills I want verified from a fixed, autocompleted list, so that my claims map to a consistent taxonomy recruiters can compare across candidates.
3. As a Candidate, I want a stable identity across visits, so that logging in again lets me refresh my existing profile instead of starting over.

**Candidate — verification and scoring**

4. As a Candidate, I want to kick off verification and see a "processing" status, so that I know the system is working even though scoring may take a while.
5. As a Candidate, I want each of my claimed skills to get its own Confidence Score, so that I can see how strongly my GitHub history actually supports that specific claim.
6. As a Candidate, I want to see exactly which commits and PR comments were used as evidence for a skill, so that I trust the score reflects real work, not a black box.
7. As a Candidate, I want a skill with zero supporting evidence to clearly show 0 confidence and no evidence, so I'm not misled into thinking a weak claim was verified.
8. As a Candidate, I want commits that only touch docs or config files excluded from scoring, so trivial changes don't inflate my confidence score.
9. As a Candidate, I want short, low-effort PR comments (like "LGTM") excluded from scoring, so score inflation from spam-like comments isn't possible.
10. As a Candidate, I want commits I've made to repositories I don't own (e.g. merged open-source PRs) to count as evidence, so my contributions elsewhere are represented, not just my own repos.
11. As a Candidate, I want only my public repositories used as evidence, so my private/proprietary code is never touched by SkillProof.
12. As a Candidate, I want a skill I've used consistently over a long period to score higher than one touched in a single burst, so sustained experience is reflected, not just a lucky matching diff.

**Candidate — explanation**

13. As a Candidate, I want a plain-English explanation of why I scored the way I did, so a recruiter can understand my evidence without decoding a raw number.
14. As a Candidate, I want a sensible fallback explanation to appear even if the LLM generating it is temporarily unavailable, so my card is never left blank or confusing.

**Candidate — sharing and re-verifying**

15. As a Candidate, I want my Evidence Card reachable via a public link, so I can share it directly in a resume, application, or LinkedIn instead of a document.
16. As a Candidate, I want to re-run verification later, so new commits and PRs I've made since last time count toward my score.
17. As a Candidate, I want re-verification to be a single click instead of reconnecting GitHub every time, so refreshing my card doesn't feel like starting over.
18. As a Candidate, I want to know if GitHub access has been revoked, so I understand why re-verification failed and how to fix it.

**Candidate — discoverability**

19. As a Candidate, I want to explicitly opt in to being discoverable by recruiters, so my profile is never searchable without my consent.
20. As a Candidate, I want opting out of search to leave my direct Evidence Card link working, so declining discovery doesn't break links I've already shared.

**Recruiter — search**

21. As a Recruiter, I want to search for candidates by a single skill tag and a minimum confidence score, so I can quickly find people who've demonstrably used that technology.
22. As a Recruiter, I want search results ranked by confidence score descending, so the strongest matches surface first.
23. As a Recruiter, I want each search result to link to the candidate's GitHub profile and their Evidence Card, so I can verify the claim myself in one click.
24. As a Recruiter, I want to use search without creating an account or logging in, so there's no friction between finding a claim and verifying it.
25. As a Recruiter, I want only candidates who've explicitly opted in to appear in results, so I'm never seeing a profile the candidate didn't consent to share.

**Platform**

26. As the SkillProof system, I want to compute Confidence Scores using only local, free embedding models, so per-candidate verification costs nothing regardless of scale.
27. As the SkillProof system, I want scoring to never depend on an LLM call, so the core verification signal stays deterministic and reproducible.
28. As the SkillProof system, I want to generate skill explanations lazily, only on first view, so LLM usage is proportional to actual traffic, not verification volume.
29. As the SkillProof system, I want a generated explanation cached on the Evidence Card, so repeated views don't re-trigger LLM calls.
30. As the SkillProof system, I want GitHub API calls to respect rate limits via conditional requests and exponential backoff, so verification doesn't get the service throttled or banned.
31. As the SkillProof system, I want `/verify` to run asynchronously, so a candidate with many repos doesn't hit an HTTP timeout while scoring runs.
32. As the SkillProof system, I want `/search` rate-limited per IP, so bulk scraping of the candidate index isn't trivially possible.
33. As the SkillProof system, I want each Candidate keyed by a stable internal ID distinct from their GitHub username, so public URLs don't break if they rename their GitHub account.

## Implementation Decisions

**Actors.** Two actors, neither with symmetric accounts: the Candidate (the single authenticated actor — connects GitHub, claims Skill Tags, owns a persistent identity) and the Recruiter (unauthenticated, stateless — no login, no saved state, one capability: search).

**GitHub ingestion.** OAuth with read-only, public scope. Pulls commit diffs and PR review comments from (a) the Candidate's own public, non-fork repos, and (b) external repos where the Candidate has at least one merged PR (discovered via the GitHub Search/Events API). Respects GitHub rate limits via conditional requests (ETags) and exponential backoff on secondary rate limits.

**Heuristic pre-filter.** Runs before embedding: drops commits that touch only docs/config files, and drops PR comments under 10 words.

**Skill taxonomy and embedding.** A fixed, hand-curated Skill Tag taxonomy (roughly 100-150 entries — languages, frameworks, datastores, infra/tools) is embedded once locally and cached. Candidates select claims from this taxonomy via autocomplete; free-text claims are not supported. Evidence embedding uses a local sentence-transformer model (no paid or external embedding API).

**Confidence Score (never LLM-touched — see ADR-0001).** Per Evidence Item, cosine similarity against the claimed Skill Tag's embedding. An item only qualifies as evidence if similarity is ≥ 0.35. Confidence Score is the mean similarity of the top 5 qualifying items (fewer than 5 if fewer qualify — never padded). Zero qualifying items yields `confidence_score = 0`, `evidence_type = "none"`, `source_commits = []`. A temporal multiplier — 1.0 at a qualifying-evidence span of ≥90 days, scaling linearly down to 0.7 at a 0-day span, measured across the *full* qualifying set rather than just the top 5 — is applied: `confidence_score = top5_mean × temporal_multiplier`, clamped to [0,1].

**Explanation layer (see ADR-0001).** A one-sentence justification per skill, generated by Groq (Llama 3.3 70B, free tier, OpenAI-compatible API), triggered lazily on first view of an Evidence Card that lacks a cached Explanation — not part of the verify job. Built from the same qualifying Evidence Items used in scoring, and cached on the card once generated. On LLM failure or rate-limiting, a deterministic template sentence built from evidence stats (commit count, repo count, day span) stands in until a later call succeeds.

**Candidate identity and re-verification (see ADR-0003).** First GitHub login creates a Candidate record mapping the GitHub user ID to an internal `candidate_id` (UUID); later logins reuse it. Public URLs use `candidate_id`, never the GitHub username. The GitHub OAuth token is stored encrypted at rest and reused for re-verification without a fresh OAuth redirect; a revoked token fails the next verify attempt gracefully and prompts reconnection. Re-verification overwrites the existing Evidence Card per Skill Tag in place — no history or versioning in MVP.

**Verification job.** `/verify` is asynchronous: it returns immediately (processed via an in-process background task, no separate queue/worker infrastructure), and the client polls for status while Evidence Cards populate per skill as scoring completes.

**Search and discoverability (see ADR-0002).** A per-Candidate `searchable` boolean, defaulting to `false`, is opted into via a checkbox shown when generating the Evidence Card — it gates inclusion in search results only, never direct card access. `/search` takes a skill tag and a minimum confidence score, filters to `searchable = true` Candidates, returns results sorted descending by confidence (GitHub profile link + Evidence Card link per result), capped at a fixed result limit rather than paginated. No recruiter accounts or authentication. Rate-limited to 60 requests/minute per IP.

**Storage.** SQLite for MVP (Postgres for later deployment). A Candidate record holds the GitHub user ID, `candidate_id`, encrypted token, and `searchable` flag. An Evidence Card record (keyed by candidate + Skill Tag) holds the confidence score, evidence type, source commit references, temporal span, and cached explanation.

**API surface.** GitHub OAuth entry point; a verify-trigger endpoint plus a status check; Evidence Card retrieval by `candidate_id`; an explain-generation endpoint per candidate+skill; and the search endpoint.

## Testing Decisions

A good test here asserts on external behavior — given fixture GitHub data, does the resulting Evidence Card or search response look right — never on internal call counts or which internal module touched what.

One seam, at the FastAPI HTTP boundary: tests drive the full pipeline through the public API (connect → verify → poll → fetch Evidence Card → explain → search) via an HTTP test client, exercising ingestion, the heuristic filter, embedding, and scoring together as one real, wired-together unit rather than unit-testing each module against mocks of the others.

Two fakes, at the two unavoidable external-system boundaries:
- The GitHub API client, faked with fixture repos and canned commits/PRs, so scores are deterministic and repeatable in tests.
- The Groq client, faked to return a canned explanation in one test, and to raise/timeout in another so the template-fallback path is exercised.

Embeddings and scoring math run for real — local, deterministic, and free (ADR-0001) — never mocked.

No prior art exists in this repo yet (greenfield); this establishes the testing pattern for the project going forward — prefer one seam at the API boundary, fake only true external systems, wire everything internal together for real.

## Out of Scope

- Recruiter accounts, authentication, saved searches, candidate shortlists, messaging, or usage-based billing (ADR-0002) — revisit only if per-recruiter state becomes genuinely necessary.
- Private repository access — public repos only.
- Applicant tracking or resume upload/hosting — Evidence Cards replace resumes, so serving resumes would undercut the product's premise.
- LLM-based scoring of any kind — scoring stays embedding-only and deterministic (ADR-0001); this isn't a phase-2 item, it's a standing constraint unless a future ADR explicitly revisits it.
- Evidence Card history or versioning — re-verification overwrites in place.
- Free-text skill claims — skills are selected from the fixed taxonomy only.
- Sourcing the taxonomy from an external system (GitHub topics, StackShare, etc.) — it's a static, hand-curated list for MVP.
- Full pagination on `/search` — a hard result cap only.
- A separate job queue or worker system (Celery, Redis, etc.) for `/verify` — an in-process background task is sufficient for MVP.

## Further Notes

This spec was produced through a grilling + domain-modeling session; the resolved decisions and their rationale live in `CONTEXT.md` and three ADRs at the repo root (`docs/adr/0001-scoring-stays-deterministic-llm-only-explains.md`, `docs/adr/0002-search-is-public-consent-gated-no-recruiter-accounts.md`, `docs/adr/0003-persist-github-token-for-one-click-reverification.md`) — worth reading alongside this spec for the "why" behind each decision above.

The Skill Tag taxonomy's actual content (which ~100-150 skills) still needs to be authored — this spec assumes the taxonomy exists as a static list but doesn't enumerate it. Compiling that list is implementation work, not an open design question.
