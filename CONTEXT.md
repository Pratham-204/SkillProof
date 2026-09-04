# SkillProof

Verifies a developer's self-reported skills against their public GitHub activity, producing a public Evidence Card per claimed skill instead of a self-reported resume line.

## Language

**Candidate**:
The single authenticated actor in MVP — a developer who connects their GitHub account and claims skills to be verified.
_Avoid_: User, developer (when a more specific term is meant), account holder

**Candidate Dashboard**:
The authenticated landing page a returning Candidate reaches after login — replaces the earlier behavior of redirecting straight into `/claim`. Shows the same latest-per-skill Evidence Card set `/evidence-card/{candidate_id}` already returns, the Candidate's own shareable public Evidence Card link, and their `searchable` toggle. Distinct from the Evidence Card page itself, which stays deliberately session-blind (see round 10).
_Avoid_: Profile, account page (this is specifically the Candidate's own view of their Evidence Cards, not a broader account-settings surface)

**Evidence Card**:
The public, unauthenticated, per-skill output record: a Confidence Score, the qualifying GitHub evidence that produced it, and an optional Explanation. Retrieved at `/evidence-card/{candidate_id}` with no auth required.
_Avoid_: Report, badge, profile

**Skill Tag**:
One entry from SkillProof's precomputed taxonomy of technical skills — scoped to skills with an authorable Detection Pattern. The taxonomy is never user-editable, but it isn't static either: it grows automatically as new packages are sighted in Candidates' repos (see round 8 and ADR-0008). A purely theoretical/practice skill (e.g. System design) has no code footprint and isn't in the taxonomy until a non-GitHub verification path exists. Candidates claim skills by selecting Skill Tags via autocomplete, not by typing free text.
_Avoid_: Skill claim (as a raw string), stated skill (as free text)

**Confidence Score**:
The [0,1] number in an Evidence Card measuring how well a Candidate's GitHub evidence supports one claimed Skill Tag. Computed from four Signals — Presence, Volume, Depth, and Span — combined as a fixed weighted sum (0.20 / 0.40 / 0.25 / 0.15), not a single similarity average.
_Avoid_: Match score, similarity score (those are per-item, not the aggregate)

**Evidence Item**:
A single commit diff or PR review comment pulled from the Candidate's GitHub activity. Only counts toward a Skill Tag's Depth Signal if its commit already matched that Skill Tag's Detection Pattern (i.e. is Volume-qualifying) *and* its embedding similarity to the Skill Tag's canonical description clears the 0.35 qualifying floor — below that, or without a Volume-qualifying commit behind it, it isn't evidence at all.
_Avoid_: Signal (an Evidence Item is raw material a Signal is computed from, not a Signal itself), data point

**Detection Pattern**:
A Skill Tag's fingerprint for automatic identification in a Candidate's repos — a package identifier, import pattern, API surface marker, config filename, or (for language Skill Tags) a file extension / ecosystem-manifest marker. Drives the Presence and Volume Signals. A Skill Tag with no authorable Detection Pattern doesn't belong in the taxonomy.
_Avoid_: Keyword, trigger

**Sighting**:
A recorded occurrence of a manifest package that matches no existing Skill Tag's Detection Pattern, captured during a Candidate's `/verify` ingestion (ecosystem, package name, candidate, repo) as raw material for the self-extending taxonomy's batch publish step. Not itself evidence, and never scored — it only feeds the taxonomy-growth job (round 8, ADR-0008).
_Avoid_: Evidence Item (a Sighting is about a package unrecognized by the taxonomy, not qualifying evidence for a Skill Tag that already exists), unknown dependency

**Signal**:
One of four measurable components that combine into a Confidence Score. Presence and Volume are deterministic (a Detection Pattern match in a manifest/file-extension lookup, and a count of commits touching matched files). Depth is the one Signal that uses embeddings — comparing PR comments and commit messages from Volume-qualifying commits against the Skill Tag's canonical description, since that's natural language against natural language, the one place embeddings are actually reliable here. A commit message's similarity is discounted (×0.6) relative to a PR comment's before Depth's top-3 selection, since a commit message is Candidate-authored and self-describable, while a PR comment is meaningfully harder to game. Span measures the date range of the full qualifying evidence set.
_Avoid_: Score component

**Declared-Only**:
An Evidence Card state (`evidence_type = "declared_only"`) for a Skill Tag matched only via its Detection Pattern in a manifest, with zero Volume — the dependency is listed but no commit was ever found touching it. Produces a small nonzero Confidence Score from Presence alone, rather than zero, but is kept distinct from `verified` so a Recruiter can tell a bare listing apart from real usage history.
_Avoid_: Verified, weak evidence (this is a distinct, named state, not just a low score)

**candidate_id**:
An internal SkillProof-issued UUID identifying a Candidate, distinct from and mapped 1:1 to their GitHub user ID. Used in public Evidence Card URLs so the URL doesn't expose or depend on a mutable GitHub username.
_Avoid_: GitHub user ID (as the identifier used in URLs/APIs)

**Explanation**:
A one-sentence, LLM-generated justification for a Skill Tag's Confidence Score, derived from the same qualifying Evidence Items that drove the score. Generated lazily on first view via `POST /explain/{candidate_id}/{skill}` and cached on the Evidence Card. If the LLM call fails, a deterministic template sentence built from evidence stats stands in until a later call succeeds.
_Avoid_: Justification, summary

**Recruiter**:
An unauthenticated visitor who queries `/search` by one or more Skill Tags (AND semantics — a result must match every selected Skill Tag) to find ranked Candidates. Not a modeled account — no login, no saved state, no messaging. Distinct from a Candidate.
_Avoid_: User (when a more specific term is meant)

**Searchable**:
A per-Candidate boolean, defaulting to `false`, that a Candidate opts into (via a checkbox shown when generating their Evidence Card) to appear in `/search` results. Only gates inclusion in search — the Evidence Card itself is always reachable directly by URL regardless of this flag.
_Avoid_: Public/private (the card is always public; this flag only controls discoverability)

**Provenance Check**:
An eligibility gate applied to a Candidate's owned, non-forked repos already present in the current Evidence Bundle: for each such repo, one GitHub commit-search call checks whether its earliest commit's SHA already exists in another public repo the Candidate doesn't own. A match hard-disqualifies that repo's commits from Volume, Depth, and Span — never Presence, since a manifest declaration carries no authorship claim to dispute. Runs silently: it changes the resulting Confidence Score but is never surfaced as a visible label on the Evidence Card. See ADR-0012.
_Avoid_: Anti-gaming (that term already covers ADR-0004's separate PR-membership and Depth-discount corrections; this is a distinct, later mechanism)

**Span Ceiling**:
A multiplicative cap on the final Confidence Score, applied on top of — not instead of — Span's existing weighted contribution. Uses its own smooth saturation curve and a saturation constant larger than Span's own, so a short burst of otherwise-strong evidence can't reach a high Confidence Score the way sustained evidence over time can. Not a fifth Signal; it sits outside the four-Signal weighted sum. See ADR-0013.
_Avoid_: Signal (a Signal is one of the four weighted components that sum to the base Confidence Score; the Ceiling is a separate final adjustment)

## Resolved (round 2)

- Candidate identity is persistent: first GitHub login creates a `Candidate` record (GitHub user ID ↔ `candidate_id`); later logins reuse it. Re-verification overwrites the existing Evidence Card per Skill Tag — no history/versioning in MVP.
- An Evidence Item qualifies only above a 0.35 cosine similarity floor. Confidence Score averages whatever qualifying items exist (no padding to 5) among the top 5. Zero qualifying items → `confidence_score = 0`, `evidence_type = "none"`, `source_commits = []`.
- Temporal span is measured across the full qualifying evidence set, not just the top 5 items that drive the Confidence Score itself.
- The Skill Tag taxonomy is a small hand-curated static list (~100-150 entries) checked into the repo — no external taxonomy source for MVP.

## Resolved (round 3)

- `/verify` is asynchronous: it returns immediately and processes via an in-process background task (no separate queue/worker infra in MVP). The Candidate's Evidence Cards populate as the job completes; the client polls for status.
- The Candidate's GitHub access token is persisted (encrypted at rest, read-only public scope) so re-verification is a single click, not a fresh OAuth redirect. A revoked token fails the next verify attempt gracefully and prompts reconnect.

## Resolved (round 4)

- The explanation-layer LLM call uses Groq (free tier, OpenAI-compatible API) — chosen for a thin, swappable client and more than enough capability for a one-sentence summary. The specific model is an implementation detail in `Settings.groq_model` (`qwen/qwen3.8-27b`, having replaced the now-retired `llama-3.3-70b-versatile`), not part of this decision — Groq periodically deprecates models outright, so the glossary intentionally doesn't pin one.
- `/explain` is called lazily, only when an Evidence Card is viewed and has no cached Explanation yet — not baked into the `/verify` background job. `/verify` completion means scoring is done; explanations are generated separately, on demand.
- The Explanation prompt reuses the same qualifying Evidence Items already computed for the Confidence Score (not a separately-derived summary), keeping it traceable to `source_commits`.
- LLM failure or free-tier rate-limiting falls back to a deterministic template sentence built from evidence stats already on the card (commit count, repo count, day span) — no LLM dependency for the fallback path.

## Resolved (round 5)

- No recruiter authentication in MVP (see ADR-0002). `/search` filters to `searchable = true` Candidates only, and is rate-limited to 60 requests/minute per IP (slowapi) to blunt bulk scraping of the candidate index.

## Resolved (round 6)

- Confidence Score moves from pure embedding similarity to a hybrid of four Signals (weights: Presence 0.20, Volume 0.40, Depth 0.25, Span 0.15) — sentence-transformer embeddings compare poorly against raw code, so embedding is kept only where it's strong (Depth, natural language vs natural language) and replaced elsewhere with deterministic manifest/commit-count checks (see ADR-0004).
- The round-2 guarantee ("zero qualifying evidence → `confidence_score = 0`") now applies only when a Skill Tag is neither declared nor touched at all. A Detection Pattern match in a manifest with zero Volume produces `evidence_type = "declared_only"` and a small Presence-only score instead (see the Declared-Only term above).
- Depth uses the top 3 (not top 5) Volume-qualifying items' cosine similarity, each still subject to the round-2 0.35 qualifying floor. Span uses a saturating curve (`span_days / (span_days + 90)`) over the full qualifying set, replacing the old linear-with-0.7-floor multiplier.
- The round-2 docs/config-only commit filter is scoped to skip dropping a file that is itself a registered Detection Pattern (e.g. `Dockerfile` for the Docker Skill Tag), so config-based detection isn't filtered out before it's ever seen.
- Volume only counts commits authored by the Candidate *and*, for external (non-owned) repos, actually part of a PR the Candidate opened and had merged — not every author-matching commit in a repo where some merged PR exists. Without the PR-membership half of that check, a collaborator with direct push access could bypass review and inflate Volume; see ADR-0004.
- Depth discounts commit-message similarity by ×0.6 relative to PR-comment similarity before top-3 selection, rather than excluding commit messages outright — full exclusion would zero out Depth for solo/personal repos with no PR-review culture; see ADR-0004 and the Signal term above.
- Taxonomy entries with no authorable Detection Pattern (System design, Security engineering, Accessibility, Performance optimization, and similar practice/theoretical skills) are removed from the claimable taxonomy for this pass rather than left in permanently stuck at zero — see Notes.
- `/search` exposes `evidence_type` per result rather than excluding `declared_only` candidates — a real, honestly-computed low score stays visible rather than silently gated.
- Re-verification still overwrites an Evidence Card in place (round 2) *except* when the Skill Tag taxonomy itself has changed since the card was last computed — that case forks a new card under a new `taxonomy_version` instead of mutating the old one (see ADR-0005).
- The claims-per-verify constraint is a fixed cap of 8 Skill Tags per `/verify` call (rejected with 400 if exceeded) — not a lifetime limit. A Candidate claiming more than 8 skills total simply calls `/verify` again with the rest.

## Resolved (round 7)

- Candidate authentication moves from implicit trust to an actual session: `GET /auth/github/callback` sets an HttpOnly session cookie (opaque session id → `candidate_id`) and redirects into the frontend, rather than returning the `candidate_id` as a bare JSON body. `POST /verify` and the `searchable` toggle now require that session and derive `candidate_id` from it server-side — they no longer trust a client-supplied `candidate_id`, which was previously sufficient to trigger verification or flip `searchable` on someone else's behalf, since `candidate_id` is intentionally public (embedded in Evidence Card URLs). This is what actually makes the Candidate term's "authenticated actor" claim true; see ADR-0006.
- The frontend is served single-origin: FastAPI serves the built app, so the session cookie stays same-site (no cross-site `SameSite=None`/HTTPS-only cookie requirement). A dev-time Vite server may still front it for HMR, proxying API calls to FastAPI rather than running as a permanently separate origin.

## Resolved (round 8)

- The self-extending taxonomy (previously deferred in the Notes below) is now scoped. `/verify`'s existing manifest fetch records a Sighting for any package matching no existing Skill Tag's Detection Pattern — at no added cost or latency to `/verify` itself, and with no synchronous LLM call.
- A separate batch process, run on a fixed cadence (e.g. nightly) rather than continuously, evaluates Sightings once they've been seen across a minimum number of distinct Candidates, and publishes new Skill Tags directly — there is no human approval step. Batching (instead of publishing continuously) exists specifically to bound how often `taxonomy_version` bumps, since a bump forks every Evidence Card globally (ADR-0005), not just cards for the newly added tag.
- In place of human review, publishing is gated by: a deterministic check that the sighted package actually exists on its ecosystem's real registry; a deterministic exact/case-insensitive name dedup against the existing taxonomy; and an LLM check for semantic duplicates against existing entries' canonical descriptions, not just their names, before it drafts anything new. The LLM may also abstain — "not a real claimable skill" is a valid outcome for a Sighting that clears the deterministic checks — and its category choice is constrained to the taxonomy's existing five categories; it cannot mint new ones.
- A published Skill Tag's Detection Pattern is populated directly from the Sighting itself (the sighted ecosystem + package name become its `manifest_packages` entry) — the LLM only drafts the category and canonical description. The batch job also extends the precomputed embeddings cache for each newly published tag, since no human remains to run that step manually.
- A bad entry that slips through despite the guards is corrected the same way any hand-curated taxonomy mistake is today: a manual edit to `skills.json` and a version bump. There is no separate retraction/undo mechanism for auto-added entries.

See ADR-0008.

## Resolved (round 9)

- PR review comments are deliberately never Depth evidence for `language`-category Skill Tags (Python, JavaScript, TypeScript, Go, Rust, …). A comment has no file path of its own, so it can only match a Detection Pattern via `content_markers`/`manifest_packages` — and every language entry's `content_markers` is intentionally left empty, since generic syntax fragments (e.g. `"def "`, `"self."`) would false-positive on almost any code-review comment quoting a snippet. This is a taxonomy-design choice, not a gap to fill: language Skill Tags accrue Volume/Depth from commits (matched via file extension) only; PR comments remain a source of evidence for Skill Tags with a distinctive, low-noise API surface (frameworks/tools/infra) instead.
- The `verified`-with-zero-qualifying-items fallback explanation (see the Evidence Item term) previously used the same wording as `declared_only` — "no individual commit or PR comment qualified as evidence" — even though a `verified` card has real Volume-qualifying commits behind it; they just didn't clear Depth's 0.35 floor. The two states now get distinct wording so the explanation never contradicts `evidence_type`.

## Resolved (round 10)

- A Candidate Dashboard (see term above) becomes the authenticated landing experience: `Home`'s post-login redirect target moves from `/claim` to this new page, and "claim more skills" becomes an action reachable from the dashboard rather than the automatic post-login destination.
- The dashboard surfaces the same latest-`taxonomy_version`-per-skill card set every other Evidence Card view already uses — no new versioning/history browsing surface, matching the round-2 "no history/versioning in MVP" decision.
- The dashboard is a new, separate page/component rather than an owner-mode branch added to `PublicEvidenceCard` — that page's existing invariant (identical output regardless of viewer/session) stays intact.
- `searchable` becomes toggleable on its own via a new small authenticated endpoint, rather than only settable as a field on a `/verify` call as today.
- A recruiter-facing portal (accounts, login, saved candidates) would be a deliberate reversal of the existing "no Recruiter account" decision (see Recruiter term and Notes below) — explicitly out of scope for this round and deferred to its own future grilling session; nothing here assumes it exists.
- Frontend navigation gets persistent, viewer-agnostic nav chrome on every page, and `ScanReveal`'s claimed-skills tracking moves from trusting router `location.state` (silently lost on back-navigation or a refresh) to deriving the expected set from the Candidate's own `processing`-status cards instead — addressing the actual cause of state loss on back-navigation, not just adding a link. Sign-out/session termination is explicitly out of scope for this pass.

## Resolved (round 11)

- A new Provenance Check closes a gap ADR-0004's anti-gaming corrections didn't cover: an owned, non-forked repo's commits could still inflate Volume/Depth/Span even if that history was imported rather than genuinely authored by the Candidate. For each owned, non-forked repo already in the current Evidence Bundle, one GitHub commit-search call checks whether its earliest commit's SHA exists in another public repo the Candidate doesn't own; a match hard-disqualifies that repo's commits from Volume, Depth, and Span (not Presence). See ADR-0012.
- The Provenance Check is deliberately silent: a match changes the Confidence Score but is never surfaced as a visible label on the public, unauthenticated Evidence Card. Publishing an automated fraud-adjacent accusation with no dispute mechanism is a separate, weightier product decision, out of scope here.
- A positive Provenance Check match is cached permanently once found; a clean result is re-checked on each future re-verification rather than cached, since the absence of a match today isn't a permanent guarantee.
- A new Span Ceiling caps the final Confidence Score based on sustained activity, addressing a gap the existing formula's purely additive Span weight left open: a short, intense burst of Volume/Depth evidence could previously reach a high score discounted by no more than Span's 15% share. The Ceiling is a separate multiplicative factor layered on top of the existing weighted sum — not a replacement for Span's weight, and not a fifth Signal — using its own saturation curve and a constant distinct from (and larger than) Span's own `SPAN_SATURATION_DAYS`. See ADR-0013.
- Surveyed five open-source repos (gitfut, gh-fake-analyzer, GitHub-Profile-Analyzer, ossinsight, gitinspector) for reusable scoring logic. Two yielded the mechanisms above; GitHub-Profile-Analyzer, ossinsight, and gitinspector had no transferable scoring algorithm on inspection — only descriptive visualizations over the same raw GitHub counts SkillProof already has access to.

## Notes

- Recruiter has exactly one capability (`/search`) and no account — see the Recruiter, Searchable, and Explanation terms above.
- `/search` takes a hard result cap (e.g. `limit=50`), not full pagination — an implementation default, not a design branch.
- `/search` caps a query at 8 Skill Tags (rejected with 400 if exceeded), mirroring `/verify`'s existing 8-skill cap. Results are ranked by the average Confidence Score across only the queried skills; see ADR-0007 for the AND semantics and per-skill result breakdown.
- Explicitly out of scope: recruiter accounts/auth, saved searches, candidate messaging, applicant tracking, resume upload/hosting — Evidence Cards replace resumes, so serving resumes would undercut the product's premise.
- The self-extending taxonomy is scoped as of round 8 above (see ADR-0008) — parsing unknown manifest packages into Sightings, then auto-publishing new Skill Tags via deterministic registry/dedup checks plus an LLM draft-or-abstain step, with no human approval gate. One follow-on feature remains deferred without its own scoping session yet: a **Depth Interview** (an unscored, LLM-conducted conversational artifact for skills with no code footprint — code-anchored, probing a specific commit, or experience-anchored, probing a Candidate's self-described private/internship work); it gets its own grilling session before further design. Multi-platform evidence sourcing (LeetCode, HackerRank, etc.) is a further-out idea, not yet scoped at all.
