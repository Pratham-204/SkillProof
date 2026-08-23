# Candidate writes move from trusting a client-supplied candidate_id to a session cookie

Building a browser frontend surfaced a latent gap: `POST /verify` and the `searchable` toggle took `candidate_id` straight from the request body with no session check, and `candidate_id` is intentionally public (it's embedded in Evidence Card URLs). Anyone who'd seen a Candidate's card already had everything needed to re-trigger their verification or flip their `searchable` flag. `GET /auth/github/callback` now sets an HttpOnly session cookie (opaque session id → `candidate_id`) and redirects into the frontend instead of returning `candidate_id` as a JSON body; `/verify` and the `searchable` toggle derive `candidate_id` from that session server-side and no longer accept a client-supplied one. The frontend is served single-origin (FastAPI serves the built app; Vite only fronts it for dev-time HMR, proxying to FastAPI) specifically so the cookie can stay same-site rather than requiring `SameSite=None` + HTTPS-only.

## Considered Options

Keep `candidate_id` as the sole key, passed by the frontend on every write (rejected — leaves the pre-existing gap unresolved). A separate short-lived bearer token distinct from `candidate_id`, sent as a header with no cookie/session infra (rejected — still means hand-rolling session semantics without the browser's built-in cookie handling, for no real savings once a frontend exists).

## Reversal trigger

If the frontend ever needs to run on a genuinely separate origin from the API (e.g. a third-party embed), this needs revisiting — same-site cookies stop working and the auth model has to move to cross-site cookies or bearer tokens.
