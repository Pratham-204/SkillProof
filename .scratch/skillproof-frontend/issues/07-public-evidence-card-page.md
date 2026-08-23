# 07 — Public Evidence Card page

**What to build:** A shareable, unauthenticated route (`/c/:candidateId`) that fetches `GET /evidence-card/{candidate_id}` and replays the same reveal component from ticket 05 against the already-complete card list — no live scan phase, since there's nothing to scan.

**Blocked by:** 02, 06.

**Status:** done

- [x] `/c/:candidateId` requires no session/auth — matches the backend's `/evidence-card/{candidate_id}` being fully public.
- [x] The page skips `scanning` phase entirely (no SSE, nothing in progress) and enters `revealing` directly against the fetched, already-complete card list, staggering cards in the same way a live reveal would.
- [x] Card detail expansion (ticket 06) works identically here, including lazy Explanation fetch.
- [x] An unknown/invalid `candidate_id` shows a clear not-found state, not a blank page or a raw error.
- [x] A Candidate visiting their own public link (still logged in, same browser) sees the same public view — this page never exposes owner-only actions (re-verify, searchable toggle); those live only on the authenticated claim/dashboard views.

## Comments

**Implementation:** `PublicEvidenceCard.tsx` fetches `GET /evidence-card/{candidateId}` on mount and renders one of three states: loading (`null`, no flash), not-found (any fetch failure — 404 or otherwise — is treated as not-found, since an invalid `candidate_id` is the only plausible failure mode here), or the card list. It never calls `getMe()` or checks any session — deliberately session-blind, so a Candidate viewing their own link gets byte-for-byte the same page a stranger would, with no owner-only affordances to accidentally leak in.

Reused `EvidenceCardTile`/the reveal choreography from ticket 05 rather than duplicating it: extracted a small `components/EvidenceCardList.tsx` (the `motion.ul` + `staggerChildren` variants + tile mapping) that `ScanReveal.tsx` now also uses in its `revealing`/`complete` phases, so the exact same stagger animation and tile rendering (including ticket 06's expand-to-explain) is guaranteed to behave identically on both the live and public paths, not just similarly.

**Verified live** (see ticket 04/05's updates for how the real account/data was set up): visited `/c/{realCandidateId}` directly — staggered reveal played with no scan phase, correct verified/none card styling; visited `/c/not-a-real-id` — clean "Not found" state, no blank page or console error; navigated here via the search page's "View Evidence Card" link (ticket 08) using client-side routing (`react-router-dom`'s `Link`) — confirmed no full page reload. `tsc -b`, `vite build` (436 modules), and `oxlint` all clean (one pre-existing accepted warning in `ScanReveal.tsx`, unrelated to this ticket).
