# 02 — App shell, routing, and single-origin serving

**What to build:** The Vite + React + TypeScript + Tailwind scaffold, wired so FastAPI serves the built app in place of a bare JSON root, with a Vite dev server proxy for local development. Establishes the route skeleton the other frontend tickets fill in.

**Blocked by:** none.

**Status:** done

- [x] Vite + React + TypeScript project scaffolded (location: implementer's call, e.g. `frontend/`), with Tailwind CSS configured.
- [x] Fonts wired via Google Fonts: Instrument Serif or Fraunces (wordmark), Inter (UI), JetBrains Mono (hashes/scores).
- [x] `font-variant-numeric: tabular-nums` applied as a reusable utility/class for animated numbers.
- [x] FastAPI mounts the built app's static output and serves it for all non-API routes (a catch-all that doesn't shadow the existing `/auth`, `/verify`, `/evidence-card`, `/explain`, `/search`, `/skills` routes).
- [x] Vite's dev server proxy config forwards those same API paths to the FastAPI dev server (`:8000`), so `npm run dev` gives working HMR against a real local backend with no CORS middleware added anywhere.
- [x] Client-side routing (`react-router-dom` or equivalent) has stub routes for: home/connect, claim-skills, live scan/reveal, public Evidence Card (`/c/:candidateId`), and search — each rendering a placeholder, to be filled in by later tickets.
- [x] `README.md` gets a short frontend dev-setup section (install, `npm run dev`, `npm run build`) alongside the existing backend setup instructions.

## Comments

Implementation: `frontend/` (Vite + React 19 + TS + Tailwind v4 via `@tailwindcss/vite` + Framer Motion + react-router-dom, all installed as direct deps — no fifth animation/state library per the spec). Fonts: Fraunces (wordmark), Inter (UI), JetBrains Mono — loaded via Google Fonts `<link>` tags in `index.html`. `tabular-nums` uses Tailwind's built-in utility rather than a hand-rolled class (Tailwind ships `font-variant-numeric: tabular-nums` out of the box).

Frontend routes: `/`, `/claim`, `/scan`, `/c/:candidateId`, `/find` (recruiter search — named `/find`, not `/search`, because `/search` is one of the backend API path prefixes the dev proxy forwards to FastAPI; reusing it would shadow the API on direct navigation/refresh). `src/main.py` mounts `frontend/dist/assets` and adds a catch-all `GET /{full_path:path}` route, registered after every API router, that serves a matching static file if one exists or falls back to `index.html` for SPA routes — skipped entirely if `frontend/dist` doesn't exist yet, so backend-only dev/tests are unaffected. Manually smoke-tested end to end: `npm run build` then running the app directly confirmed `/` serves the built app, `/scan` (a client-side route) falls back to `index.html` (200, not 404), `/skills` still returns real API JSON, and a built JS asset under `/assets/` resolves. Full backend suite (75 tests) and `mypy` stay clean.
