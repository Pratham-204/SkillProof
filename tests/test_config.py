"""Ticket 09 (production readiness): SKILLPROOF_TOKEN_ENCRYPTION_KEY must be
required outside dev, and the session cookie's Secure attribute should default
on in production without needing a second env var — see config.py's
`_resolve_production_defaults` validator.
"""

import pytest

from skillproof.config import Settings


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
