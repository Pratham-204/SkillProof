# SkillProof Frontend

Status: ready-for-agent

## Problem Statement

SkillProof's backend (MVP + hybrid scoring) is complete and fully tested, but the product has no way for a human to actually use it: every flow — connecting GitHub, claiming skills, watching verification run, reading an Evidence Card, searching candidates — is API-only. There's also a latent security gap in the API surface: `POST /verify` and the `searchable` toggle currently trust a client-supplied `candidate_id`, which is intentionally public (it's embedded in Evidence Card URLs), so anyone who's seen a Candidate's card already has what they need to trigger verification or flip `searchable` on that Candidate's behalf. Building a real frontend puts a UI in front of that gap, so closing it is part of this pass, not a follow-on.

This build targets a hackathon submission, with hosting on a purchased domain planned once the product side is done — see Further Notes.

## Solution

A Vite + React + TypeScript + Tailwind + Framer Motion single-origin app, served by FastAPI (the built app is what FastAPI serves in place of a bare JSON root; Vite only fronts it during development, proxying API calls, never as a permanent second origin). Candidate authentication becomes a real HttpOnly session cookie set at the OAuth callback, replacing the current trust-the-request-body model (ADR-0006). The centerpiece is the claim → scan → reveal flow: a Candidate picks skills, verification runs with real per-repo progress streamed over SSE (repo names narrated as they're scanned), and results arrive as a staggered, per-skill reveal (Framer Motion `staggerChildren`, animated score count-up with `tabular-nums`, floored at a 1.5s minimum so a fast verification never collapses the effect). The same reveal component renders a public Evidence Card link on load (no live scan, but the same staggered arrival), so a cold shared link still feels like the product. A separate, unauthenticated Recruiter search page rounds out the three modeled actors' flows.

## User Stories

**Candidate — connecting and claiming**

1. As a Candidate, I want to connect my GitHub account and land in the app already signed in, so nothing about the OAuth round-trip feels broken or exposes raw JSON in my browser.
2. As a Candidate, I want to pick the skills I want verified from an autocomplete list capped at 8, so I can't submit a claim set the backend will reject.
3. As a Candidate, I want to opt into being searchable at the same point I submit my claims, so discoverability is a deliberate choice made once, not a separate hunt through settings.

**Candidate — scan and reveal**

4. As a Candidate, I want to see my own repos named as they're scanned, so waiting for verification feels like watching something real happen, not staring at a spinner.
5. As a Candidate, I want my Evidence Cards to arrive one at a time in a staggered sequence as each skill finishes scoring, so the reveal reflects real per-skill completion, not a fake animation over a single lump of data.
6. As a Candidate, I want a fast verification to still take a perceptible moment before revealing, so the reveal never collapses into an instant, anticlimactic flash.
7. As a Candidate, I want a skill with weak or `declared_only` evidence to look visibly different from a strongly verified one, so the reveal doesn't visually flatter a claim the score itself doesn't support.

**Candidate — card detail and sharing**

8. As a Candidate, I want to see the specific commits and PR comments behind a score without leaving the card, so I can check the evidence myself.
9. As a Candidate, I want the plain-English explanation to load only when I ask for it, so viewing my cards doesn't wait on a third-party LLM call I may not even read.
10. As a Candidate, I want a public link to my Evidence Card that plays the same reveal a first-time viewer would see live, so sharing it doesn't feel like a lesser, static version of the product.
11. As a Candidate, I want a clear reconnect prompt if my GitHub token was revoked, so a failed re-verification tells me what to do instead of failing silently.

**Recruiter — search**

12. As a Recruiter, I want to search by skill and minimum confidence and see ranked, linked results, so I can act on a match without creating an account.

**Platform**

13. As the SkillProof system, I want a Candidate's session to be the only thing that can trigger verification or change their `searchable` flag on their behalf, so a publicly-known `candidate_id` is never sufficient to act as that Candidate.
14. As the SkillProof system, I want the frontend and API served from one origin, so the session cookie never needs cross-site cookie handling to work.
15. As the SkillProof system, I want real, incremental progress signals from the verification pipeline (per repo scanned, per skill scored), so the scan/reveal UI is never narrating or animating fabricated progress.

## Implementation Decisions

**Auth (see ADR-0006).** `GET /auth/github/callback` sets an HttpOnly session cookie (opaque session id → `candidate_id`) and redirects into the frontend app instead of returning `CandidateOut` as a JSON body. `POST /verify` and the `searchable` toggle read `candidate_id` from the session server-side and no longer accept one from the request; `VerifyRequest.candidate_id` is dropped from the client-facing payload accordingly. Session cookie is `Secure` outside local dev.

**Serving model.** FastAPI mounts the built Vite app (`dist/`) as static files and serves it for all non-API routes. In development, the Vite dev server runs separately for HMR but proxies `/auth`, `/verify`, `/evidence-card`, `/explain`, `/search`, and `/skills` to FastAPI — it is not a permanent second origin, and no `CORSMiddleware` is added.

**Verify progress streaming.** A new SSE endpoint (`GET /verify/{candidate_id}/stream`, `sse-starlette`) reports two kinds of real events: scan events (one per repo, as `ingest_evidence` processes it — requires threading a progress callback through `ingestion.py` and the relevant `GitHubClient` calls, which today run as one opaque blocking call) and reveal events (one per skill, emitted as `run_verification`'s scoring loop commits each `EvidenceCard` individually instead of batching one commit at the end, as it does today). The stream closes once all claimed skills report `complete` or `failed`.

**Reveal choreography.** A four-phase state machine (`idle | scanning | revealing | complete`) drives a single page: `scanning` consumes scan SSE events (repo names) and enforces a 1.5s minimum before advancing; `revealing` consumes reveal SSE events and staggers each arriving card in via Framer Motion (`staggerChildren`); `complete` shows the full set with `EvidenceCardOut.evidence_type` driving a distinct visual treatment for `declared_only` and `none` versus `verified`. The public Evidence Card page reuses this same reveal component in `revealing`→`complete` mode against an already-complete card list (no SSE, no scan phase).

**Explanation.** Fetched from `POST /explain/{candidate_id}/{skill}` lazily, on user interaction with a specific card (e.g. expand), not during the reveal sequence — matches the backend's existing on-demand design and keeps the reveal independent of Groq latency.

**Stack.** Vite + React + TypeScript + Tailwind CSS + Framer Motion only — no component library (shadcn rejected: this is a handful of bespoke cards and one button, not a form-heavy app), no state library beyond `useState<Phase>`. Fonts: Instrument Serif or Fraunces for the wordmark, Inter for UI text, JetBrains Mono for commit hashes and scores (all Google Fonts). `font-variant-numeric: tabular-nums` on every animated number, to prevent digit-width jitter during count-up.

**Pages/routes.** Home/connect, claim-skills, the live scan/reveal view, a shareable public Evidence Card route (`/c/:candidateId`, distinct from the API's `/evidence-card/{id}`), and the search page. Client-side routing (`react-router-dom`) is an implementation detail, not an open design question.

**Production readiness (for hosting on a purchased domain).** `SKILLPROOF_TOKEN_ENCRYPTION_KEY` must be an explicit, persisted Fernet key outside local dev (the current default — a fresh key generated per process — silently breaks stored-token decryption on every restart); the session cookie's `Secure` flag and `SKILLPROOF_GITHUB_OAUTH_REDIRECT_URI` must both reflect the real deployed domain once one exists. None of this requires CORS configuration, per the single-origin decision above.

## Testing Decisions

Same one seam as the existing suite (`tests/conftest.py`, `tests/test_api_flow.py`): drive backend changes (session cookie auth, SSE progress events) through the FastAPI HTTP test client, faking only GitHub and Groq as before. The SSE endpoint is tested by consuming the stream in-test and asserting on the sequence of event types/payloads, not by asserting on internal call counts.

Frontend testing is component/interaction-level (React Testing Library) for the phase state machine and card rendering logic — no new end-to-end browser test infrastructure is introduced in this pass; manual verification via `/run` against a real (fixture-backed) backend is the primary check for the reveal choreography and animation feel, which isn't meaningfully assertable in a unit test.

## Out of Scope

- **Actual hosting and domain purchase/DNS setup** — these are human-gated steps (buying a domain, provisioning a host, setting DNS records) that belong to a guided walkthrough (the `wizard` skill) once the product side of this spec is built and working locally, not implementation tickets in this batch.
- **Cross-site deployment** (frontend and API on genuinely separate origins/domains) — the single-origin decision this spec makes means `SameSite=None`/cross-site cookie handling is explicitly not built; see ADR-0006's reversal trigger if that ever changes.
- **A job queue or worker system for `/verify`** — unchanged from the MVP; still an in-process background task, now additionally observable via SSE.
- **Evidence Card history/versioning in the UI** — unaffected by this spec; a re-verify still overwrites in place (or forks on a taxonomy bump) exactly as the backend already does.
- **Recruiter accounts** — unaffected; search stays fully unauthenticated per ADR-0002.
- **New animation/UI libraries beyond Framer Motion** (react-countup, XState, shadcn) — deliberately rejected; see Implementation Decisions.

## Further Notes

This spec was produced through a grilling + domain-modeling session; the resolved decisions live in `CONTEXT.md` (round 7) and `docs/adr/0006-session-cookie-auth-for-candidate-writes.md`.

The hackathon submission target and hosting/custom-domain plan were raised after the design session settled scope — they don't change any decision above (the single-origin, session-cookie architecture was already the right shape for eventually hosting under one domain), but they do mean tickets 01–08 (the product) should be prioritized over ticket 09 (production-hardening config), which only matters once an actual deploy is imminent.
