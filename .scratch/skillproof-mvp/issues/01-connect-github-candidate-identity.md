# 01 — Connect GitHub & establish Candidate identity

**What to build:** A user completes the GitHub OAuth flow (read-only, public scope) and lands with a persistent Candidate identity. The first login creates a Candidate record; later logins from the same GitHub account reuse it rather than creating a duplicate.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Hitting the GitHub OAuth entry point completes a read-only, public-scope authorization and results in an authenticated Candidate.
- [x] First-time login creates a Candidate record mapping the GitHub user ID to a newly generated `candidate_id` (UUID); the GitHub access token is stored encrypted at rest.
- [x] A second login from the same GitHub account reuses the existing `candidate_id` rather than creating a new Candidate record.
- [x] `candidate_id`, not the GitHub username, is the identifier returned to the client and used in subsequent API calls.
