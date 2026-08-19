from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKILLPROOF_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./skillproof.db"

    github_client_id: str = "dev-client-id"
    github_client_secret: str = "dev-client-secret"
    github_oauth_redirect_uri: str = "http://localhost:8000/auth/github/callback"
    github_oauth_scope: str = "read:user"

    # Fernet key for encrypting stored GitHub tokens at rest. Must be a valid
    # Fernet key (32 url-safe base64-encoded bytes). A fresh key is generated
    # by default so the app boots in dev without setup; set an explicit key
    # in production so encrypted tokens survive a restart.
    token_encryption_key: str = Fernet.generate_key().decode()

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    embedding_model_name: str = "all-MiniLM-L6-v2"

    evidence_qualifying_floor: float = 0.35
    top_n_evidence: int = 5
    temporal_full_credit_days: int = 90
    temporal_min_multiplier: float = 0.7

    search_rate_limit: str = "60/minute"
    search_result_limit: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()
