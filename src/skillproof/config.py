import logging
from functools import lru_cache
from typing import Self

from cryptography.fernet import Fernet
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKILLPROOF_", env_file=".env", extra="ignore")

    # "development" (default, permissive local-dev fallbacks) or "production"
    # (ticket 09) — set SKILLPROOF_ENVIRONMENT=production before deploying
    # anywhere reachable outside localhost. Nothing else in this class reads
    # this directly except the validators below.
    environment: str = "development"

    # An explicit validation_alias bypasses env_prefix for this field only
    # (every other field keeps requiring its SKILLPROOF_ prefix): Railway's
    # Postgres addon, like "most Postgres hosts" (db.py's own docstring),
    # injects a bare DATABASE_URL, not a SKILLPROOF_-prefixed one, so this
    # field must accept that directly or it silently never binds — the app
    # would keep using the SQLite default against a real Postgres addon
    # sitting right there unused (skillproof-deployment ticket 05).
    # SKILLPROOF_DATABASE_URL still wins if both happen to be set.
    database_url: str = Field(
        default="sqlite:///./skillproof.db",
        validation_alias=AliasChoices("SKILLPROOF_DATABASE_URL", "DATABASE_URL"),
    )

    github_client_id: str = "dev-client-id"
    github_client_secret: str = "dev-client-secret"
    github_oauth_redirect_uri: str = "http://localhost:8000/auth/github/callback"
    # `repo` (not just `read:user`) so a Candidate's private repos are visible
    # to list_owned_repos too — GitHub's classic OAuth scopes have no
    # read-only-private-repos option; `repo` is the only scope that reads
    # private repo content at all, and it nominally grants write access this
    # app never exercises. A Candidate who authorized under the old, narrower
    # scope keeps working (github_client.list_owned_repos falls back to
    # public-only for them) until they reconnect.
    github_oauth_scope: str = "read:user repo"

    # Fernet key for encrypting stored GitHub tokens at rest. Must be a valid
    # Fernet key (32 url-safe base64-encoded bytes). Left unset by default —
    # the validator below either fills in a fresh per-process key (dev) or
    # refuses to start (production), rather than silently generating one in
    # both cases. A fresh key generated on every restart/redeploy would make
    # every previously-stored GitHub token permanently undecryptable, forcing
    # every Candidate to reconnect (this actually happened in local testing).
    token_encryption_key: str = ""

    groq_api_key: str = ""
    # Groq periodically retires models outright (this replaced llama-3.3-70b-versatile,
    # which started 404ing with model_not_found — not a key/rate-limit issue, the model
    # was just gone). Deliberately not one of Groq's "gpt-oss" reasoning models: those
    # spend hidden `reasoning` completion tokens out of the same fixed max_tokens budget
    # below before ever writing visible content, and on this app's actual explanation
    # prompts (not just simple ones) that reliably burned the entire 120-token budget on
    # reasoning and returned empty content with finish_reason="length" — a "successful"
    # call by `_post_chat`'s old contract that silently cached a blank explanation.
    # qwen3.8-27b isn't a reasoning model at all (no hidden token spend) and produced a
    # clean sentence within budget on every real prompt this app generates.
    groq_model: str = "qwen/qwen3.8-27b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    embedding_model_name: str = "all-MiniLM-L6-v2"

    evidence_qualifying_floor: float = 0.35

    search_rate_limit: str = "60/minute"
    search_result_limit: int = 50

    session_cookie_name: str = "skillproof_session"
    # `CandidateSession` rows never expire server-side (deps.py's
    # get_current_candidate has no TTL check), but the cookie previously had no
    # max_age/expires at all — making it a browser-lifetime-only cookie, so a
    # Candidate got silently logged out on perfectly ordinary browser behavior
    # (browser fully closed and reopened, "clear cookies on exit", etc.), not
    # just an actual sign-out. 30 days, non-refreshing: this is a read-only
    # GitHub-scope session with no competing "log me out" UX (sign-out is
    # explicitly out of scope per CONTEXT.md round 10), so there's no reason to
    # make a Candidate reconnect more often than ADR-0003's whole point of
    # persisting the GitHub token in the first place.
    session_max_age_days: int = 30
    # False so local dev over plain http:// works — a Secure cookie is
    # silently dropped by browsers over http://, which would break login, not
    # just weaken it. Defaults to True instead whenever environment=production
    # and this wasn't explicitly set (see validator below), so a production
    # deploy doesn't also need a second env var just to get a secure cookie.
    session_cookie_secure: bool = False
    # Where a browser lands after GET /auth/github/callback sets its session
    # cookie. Relative by default since the frontend is served single-origin
    # by this same app (ADR-0006) — override only for a genuinely separate
    # frontend origin during development. Points straight at the Candidate
    # Dashboard rather than "/": "/" is always the marketing landing page now
    # (skillproof-landing-page-always-visible), so a fresh login landing
    # there instead of the dashboard would be a regression, not a detour.
    # The two OAuth failure branches in callback() share this same setting —
    # a failed login redirects to /dashboard too, and gets bounced back to
    # "/" by the dashboard's own auth guard; that extra hop is accepted for
    # now rather than adding a separate failure-redirect setting.
    github_oauth_success_redirect: str = "/dashboard"

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

        # Catches a malformed key (not 32 url-safe base64-encoded bytes) at
        # startup instead of on the first OAuth login — security.py's
        # encrypt_token() constructs a Fernet the same way with no try/except
        # around it, so an invalid key used to crash every single login with
        # an unhandled 500 instead of failing the deploy up front.
        try:
            Fernet(self.token_encryption_key.encode())
        except ValueError as exc:
            raise ValueError(
                "SKILLPROOF_TOKEN_ENCRYPTION_KEY is not a valid Fernet key (must "
                "be 32 url-safe base64-encoded bytes, e.g. the output of "
                "`Fernet.generate_key()`) — every GitHub OAuth login would "
                "otherwise crash trying to encrypt the token with it."
            ) from exc

        if self.environment == "production":
            fields = type(self).model_fields
            if (
                self.github_client_id == fields["github_client_id"].default
                or self.github_client_secret == fields["github_client_secret"].default
            ):
                raise ValueError(
                    "SKILLPROOF_GITHUB_CLIENT_ID/SKILLPROOF_GITHUB_CLIENT_SECRET must be "
                    "set to the real GitHub OAuth app's credentials when "
                    "SKILLPROOF_ENVIRONMENT=production — they're still the dev "
                    "placeholder values, so every login would fail at GitHub's "
                    "token-exchange step."
                )
            if self.database_url == fields["database_url"].default:
                raise ValueError(
                    "SKILLPROOF_DATABASE_URL (or DATABASE_URL) must point at a real "
                    "Postgres database when SKILLPROOF_ENVIRONMENT=production — it "
                    "still resolves to the local SQLite fallback (ADR-0010), which "
                    "lives on the container's ephemeral filesystem and is silently "
                    "wiped on every redeploy."
                )
            if not self.groq_api_key:
                # Not a fail-fast: explain_service already has a working
                # template-fallback path for a missing/unavailable Groq key, so
                # this shouldn't block startup — but it should be impossible to
                # miss in the logs, unlike the silent degradation this used to be.
                logger.warning(
                    "SKILLPROOF_GROQ_API_KEY is not set in production — every "
                    "/explain response will silently fall back to the deterministic "
                    "template sentence instead of an LLM-generated explanation."
                )

        if self.environment == "production" and "session_cookie_secure" not in self.model_fields_set:
            self.session_cookie_secure = True

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
