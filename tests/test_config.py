"""Ticket 09 (production readiness): SKILLPROOF_TOKEN_ENCRYPTION_KEY must be
required outside dev, and the session cookie's Secure attribute should default
on in production without needing a second env var — see config.py's
`_resolve_production_defaults` validator.

skillproof-deployment ticket 01: Railway injects DATABASE_URL as a
driver-less postgres:// (or postgresql://) URL, but SQLAlchemy needs an
explicit driver in the scheme — see db.py's `_normalize_database_url`.

skillproof-deployment ticket 05: `Settings`' blanket `env_prefix="SKILLPROOF_"`
meant `database_url` only ever bound `SKILLPROOF_DATABASE_URL` — but Railway's
Postgres addon (and "most Postgres hosts", per db.py's own docstring) injects
the platform-standard bare `DATABASE_URL`, so ticket 01's normalization never
actually ran in production; the app silently kept using ephemeral per-container
SQLite. Caught by ticket 05's persistence check against the live deployment.
"""

import pytest

from skillproof.config import Settings
from skillproof.db import make_engine


def test_development_defaults_generate_a_key_and_keep_cookie_insecure():
    # token_encryption_key="" pinned explicitly so this test is hermetic against
    # whatever the developer's own local .env happens to have set (init kwargs
    # take precedence over the dotenv file in pydantic-settings' resolution order).
    settings = Settings(environment="development", token_encryption_key="")

    assert settings.token_encryption_key  # auto-generated, not empty
    assert settings.session_cookie_secure is False


def test_production_without_an_explicit_key_fails_fast():
    with pytest.raises(ValueError, match="SKILLPROOF_TOKEN_ENCRYPTION_KEY"):
        Settings(environment="production", token_encryption_key="")


def test_production_with_an_explicit_key_boots_and_defaults_cookie_secure():
    settings = Settings(environment="production", token_encryption_key="a-real-key")

    assert settings.token_encryption_key == "a-real-key"
    assert settings.session_cookie_secure is True


def test_production_respects_an_explicit_session_cookie_secure_override():
    settings = Settings(environment="production", token_encryption_key="a-real-key", session_cookie_secure=False)

    assert settings.session_cookie_secure is False


def test_railway_style_postgres_url_gets_a_driver_scheme():
    engine = make_engine("postgres://user:pass@host:5432/railway")

    assert engine.url.drivername == "postgresql+psycopg"


def test_driverless_postgresql_url_gets_a_driver_scheme():
    engine = make_engine("postgresql://user:pass@host:5432/railway")

    assert engine.url.drivername == "postgresql+psycopg"


def test_postgres_url_with_an_explicit_driver_is_left_unchanged():
    engine = make_engine("postgresql+psycopg://user:pass@host:5432/railway")

    assert engine.url.drivername == "postgresql+psycopg"


def test_sqlite_url_is_unaffected_by_postgres_normalization():
    engine = make_engine("sqlite:///./unused-for-this-test.db")

    assert engine.url.drivername == "sqlite"


def test_bare_database_url_env_var_binds_despite_the_skillproof_prefix(monkeypatch):
    # Railway's Postgres addon injects a plain DATABASE_URL, not
    # SKILLPROOF_DATABASE_URL — Settings must accept it directly rather than
    # silently ignoring it and falling back to the SQLite default.
    monkeypatch.delenv("SKILLPROOF_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/railway")

    settings = Settings(token_encryption_key="")

    assert settings.database_url == "postgres://user:pass@host:5432/railway"


def test_skillproof_prefixed_database_url_still_wins_over_the_bare_one(monkeypatch):
    # The app's own namespaced var takes priority if both happen to be set —
    # AliasChoices checks aliases in the order given.
    monkeypatch.setenv("SKILLPROOF_DATABASE_URL", "postgres://prefixed@host:5432/railway")
    monkeypatch.setenv("DATABASE_URL", "postgres://bare@host:5432/railway")

    settings = Settings(token_encryption_key="")

    assert settings.database_url == "postgres://prefixed@host:5432/railway"
