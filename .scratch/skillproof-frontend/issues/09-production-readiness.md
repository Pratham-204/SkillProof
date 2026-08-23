# 09 — Production readiness for hosting

**What to build:** The configuration changes needed before this app can be safely hosted under a real domain — no actual hosting/domain purchase here (see spec's Out of Scope), just making the app correct once one exists.

**Blocked by:** 01, 02.

**Status:** done

- [x] `SKILLPROOF_TOKEN_ENCRYPTION_KEY` is required (fails fast at startup, not silently generated) when running outside a dev flag/environment — the current default (a fresh key per process) silently breaks stored-token decryption on every restart, which would corrupt every Candidate's stored GitHub token on redeploy.
- [x] Session cookie's `Secure` attribute is environment-driven (off for local `http://localhost`, on otherwise), building on ticket 01's session implementation.
- [x] `SKILLPROOF_GITHUB_OAUTH_REDIRECT_URI` (and the GitHub OAuth App's registered callback URL) documented as needing to match the real deployed domain — a config/documentation checklist item, not new code, since the setting already exists.
- [x] A short deployment checklist added to `README.md` covering the above three items, so they're not rediscovered under time pressure right before a hackathon submission deadline.
- [x] Confirm (by reading `main.py`) that no `CORSMiddleware` is present — the single-origin decision means none should be needed; if one was added speculatively during earlier tickets, remove it.

## Comments

This ticket is lower priority than 01–08 per the spec's Further Notes — it only matters once an actual deploy is imminent, not during initial product development. Actual domain purchase and hosting provisioning are human-gated steps for a separate `wizard`-skill walkthrough, not covered here.

**Implementation:** added a new `environment: str = "development"` setting (`SKILLPROOF_ENVIRONMENT`) to `config.py`, plus a `model_validator(mode="after")` (`_resolve_production_defaults`) that: (1) raises `ValueError` at `Settings()` construction if `environment == "production"` and `token_encryption_key` is empty — no longer silently falls back to a per-process key in that mode; (2) auto-generates a per-process key only in the dev case, exactly as before; (3) defaults `session_cookie_secure = True` when `environment == "production"` *and* the field wasn't explicitly set (checked via `self.model_fields_set`), so a production deploy only needs to set `SKILLPROOF_ENVIRONMENT` to get both protections, rather than two separate env vars — an explicit `SKILLPROOF_SESSION_COOKIE_SECURE` override still wins if someone sets one anyway.

Confirmed the fail-fast is real "at startup," not just "on first relevant request": `routers/search.py` already calls `get_settings()` at module level (inside a route decorator, `@limiter.limit(get_settings().search_rate_limit)`), and `db.py` calls it at module level too (`engine = make_engine()`) — both run during `import skillproof.main`, before uvicorn ever finishes booting. Verified directly: `SKILLPROOF_ENVIRONMENT=production` with an empty key raises `ValidationError` immediately on `import skillproof.main` (process never starts); the same import with a real key succeeds and reports `session_cookie_secure = True`.

New `tests/test_config.py` (4 tests, all pinning `token_encryption_key=""` explicitly so they're hermetic against whatever the developer's own local `.env` happens to have) covers: dev defaults (key auto-generated, cookie insecure), production without a key (raises), production with a key (boots, cookie auto-secures), and an explicit `session_cookie_secure` override in production being respected. `README.md` gained a "Deployment checklist" section covering all three env vars plus the CORS confirmation. Full suite: 83 passed.

This ticket was prompted directly by a real bug hit live in this session: restarting the backend process (to pick up code changes) repeatedly regenerated `token_encryption_key` under the old dev-only default, silently making a real Candidate's stored GitHub token undecryptable — exactly the failure mode this ticket exists to prevent in production.
