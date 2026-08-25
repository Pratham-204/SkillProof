# 02 — Frontend test infrastructure

**What to build:** The repo has no frontend test framework at all today — no Vitest, no Testing Library, no `*.test.tsx` anywhere. Wire up Vitest + React Testing Library against the existing Vite setup so every ticket after this one can carry real automated coverage instead of manual-only verification.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Vitest, `@testing-library/react`, `@testing-library/jest-dom`, and `@testing-library/user-event` are added as devDependencies and configured against the existing Vite config.
- [ ] A test script (e.g. `npm test`) runs the suite and passes.
- [ ] At least one smoke test exercises an existing component (renders it and asserts on visible output), proving the seam actually executes component code — not just that configuration loads without error.
