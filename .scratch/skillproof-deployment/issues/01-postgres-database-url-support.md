# 01 — Postgres support in config/db layer

**What to build:** `Settings`/`make_engine` correctly resolve a Railway-style `postgres://...` `DATABASE_URL` to a working SQLAlchemy Postgres connection (with the right driver dependency installed), while the existing SQLite default path (`sqlite:///./skillproof.db`) is completely unaffected. This is prefactoring — no Docker or Railway involved, purely a config/engine-construction change verified by unit tests.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] A `postgres://` or driver-less `postgresql://` URL is normalized to a scheme SQLAlchemy's chosen Postgres driver actually understands, before being handed to `create_engine`.
- [x] A URL that already specifies a driver (e.g. already `postgresql+psycopg://...`) is passed through unchanged, not double-rewritten.
- [x] The existing SQLite path (`connect_args={"check_same_thread": False}` for `sqlite`-scheme URLs) is unaffected by this change.
- [x] A Postgres driver dependency is added to `pyproject.toml`.
- [x] Covered by `tests/test_config.py` (extending the existing `Settings`/engine-construction seam from ticket 09), following that ticket's own hermetic-input pattern.
