from functools import lru_cache
from typing import Self

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKILLPROOF_", env_file=".env", extra="ignore")

    # "development" (default, permissive local-dev fallbacks) or "production"
    # (ticket 09) — set SKILLPROOF_ENVIRONMENT=production before deploying
    # anywhere reachable outside localhost. Nothing else in this class reads
    # this directly except the validators below.
    environment: str = "development"

    database_url: str = "sqlite:///./skillproof.db"

    github_client_id: str = "dev-client-id"
    github_client_secret: str = "dev-client-secret"
    github_oauth_redirect_uri: str = "http://localhost:8000/auth/github/callback"
    github_oauth_scope: str = "read:user"

    # Fernet key for encrypting stored GitHub tokens at rest. Must be a valid
    # Fernet key (32 url-safe base64-encoded bytes). Left unset by default —
    # the validator below either fills in a fresh per-process key (dev) or
    # refuses to start (production), rather than silently generating one in
    # both cases. A fresh key generated on every restart/redeploy would make
    # every previously-stored GitHub token permanently undecryptable, forcing
    # every Candidate to reconnect (this actually happened in local testing).
    token_encryption_key: str = ""

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    embedding_model_name: str = "all-MiniLM-L6-v2"

    evidence_qualifying_floor: float = 0.35

    search_rate_limit: str = "60/minute"
    search_result_limit: int = 50

    session_cookie_name: str = "skillproof_session"
    # False so local dev over plain http:// works — a Secure cookie is
    # silently dropped by browsers over http://, which would break login, not
    # just weaken it. Defaults to True instead whenever environment=production
    # and this wasn't explicitly set (see validator below), so a production
    # deploy doesn't also need a second env var just to get a secure cookie.
    session_cookie_secure: bool = False
    # Where a browser lands after GET /auth/github/callback sets its session
    # cookie. Relative by default since the frontend is served single-origin
    # by this same app (ADR-0006) — override only for a genuinely separate
    # frontend origin during development.
    github_oauth_success_redirect: str = "/"

    @model_validator(mode="after")
    def _resolve_production_defaults(self) -> Self:
        if self.environment == "production" and not self.token_encryption_key:
            raise ValueError(
                "SKILLPROOF_TOKEN_ENCRYPTION_KEY must be set explicitly when "
                "SKILLPROOF_ENVIRONMENT=production. The dev-only fallback (a fresh "
                "key generated per process) would silently make every stored GitHub "
                "token undecryptable on the next restart or redeploy."
            )
        if not self.token_encryption_key:
            self.token_encryption_key = Fernet.generate_key().decode()

        if self.environment == "production" and "session_cookie_secure" not in self.model_fields_set:
            self.session_cookie_secure = True

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
