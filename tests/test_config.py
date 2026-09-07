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

Backend/devops hardening pass: `_resolve_production_defaults` also now fails
fast in production on a still-placeholder GitHub OAuth client id/secret, a
still-default (SQLite) database_url, and a malformed token_encryption_key that
wouldn't actually construct a working Fernet cipher (previously only caught,
unguarded, on the first OAuth login — see security.py's `_fernet()`). A
missing Groq key stays a loud startup warning, not a fail-fast, since
explain_service already has a working template-fallback path for it.
"""

import logging

import pytest
from cryptography.fernet import Fernet

from skillproof.config import Settings
from skillproof.db import make_engine

_A_REAL_FERNET_KEY = Fernet.generate_key().decode()


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
    settings = Settings(
        environment="production",
        token_encryption_key=_A_REAL_FERNET_KEY,
        github_client_id="real-client-id",
        github_client_secret="real-client-secret",
        database_url="postgresql+psycopg://user:pass@host:5432/railway",
    )

    assert settings.token_encryption_key == _A_REAL_FERNET_KEY
    assert settings.session_cookie_secure is True


def test_production_respects_an_explicit_session_cookie_secure_override():
    settings = Settings(
        environment="production",
        token_encryption_key=_A_REAL_FERNET_KEY,
        github_client_id="real-client-id",
        github_client_secret="real-client-secret",
        database_url="postgresql+psycopg://user:pass@host:5432/railway",
        session_cookie_secure=False,
    )

    assert settings.session_cookie_secure is False


def test_malformed_token_encryption_key_fails_fast_with_a_clear_error():
    # Non-empty, so it clears the earlier "must be set at all" production
    # check, but not 32 url-safe base64-encoded bytes — exactly the shape
    # `security._fernet()` used to crash on, unguarded, at first login.
    with pytest.raises(ValueError, match="not a valid Fernet key"):
        Settings(environment="development", token_encryption_key="not-a-real-fernet-key")


def test_production_with_placeholder_github_credentials_fails_fast():
    with pytest.raises(ValueError, match="GITHUB_CLIENT"):
        Settings(
            environment="production",
            token_encryption_key=_A_REAL_FERNET_KEY,
            database_url="postgresql+psycopg://user:pass@host:5432/railway",
        )


def test_production_with_sqlite_fallback_database_url_fails_fast():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(
            environment="production",
            token_encryption_key=_A_REAL_FERNET_KEY,
            github_client_id="real-client-id",
            github_client_secret="real-client-secret",
        )


def test_production_without_a_groq_key_logs_a_warning_but_still_boots(caplog):
    with caplog.at_level(logging.WARNING):
        settings = Settings(
            environment="production",
            token_encryption_key=_A_REAL_FERNET_KEY,
            github_client_id="real-client-id",
            github_client_secret="real-client-secret",
            database_url="postgresql+psycopg://user:pass@host:5432/railway",
            groq_api_key="",
        )

    assert settings.groq_api_key == ""
    assert "GROQ_API_KEY" in caplog.text


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


def test_postgres_engine_pre_pings_and_recycles_and_sizes_its_pool():
    # Undocumented SQLAlchemy defaults (pool_pre_ping=False, pool_recycle=-1,
    # pool_size=5, max_overflow=10) leave a stale connection undetected and
    # size the pool for ordinary requests only, not a /verify background job
    # holding one session for its whole scan — see make_engine()'s comment.
    engine = make_engine("postgresql+psycopg://user:pass@host:5432/railway")

    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == 1800
    assert engine.pool.size() == 10
    assert engine.pool._max_overflow == 20


def test_sqlite_engine_is_unaffected_by_postgres_pool_tuning():
    engine = make_engine("sqlite:///./unused-for-this-test.db")

    assert engine.pool._pre_ping is False
