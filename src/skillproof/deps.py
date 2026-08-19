from functools import lru_cache

from skillproof.db import SessionLocal
from skillproof.github_client import GitHubClient, RealGitHubClient
from skillproof.groq_client import GroqClient, RealGroqClient


@lru_cache
def get_github_client() -> GitHubClient:
    return RealGitHubClient()


@lru_cache
def get_groq_client() -> GroqClient:
    return RealGroqClient()


def get_session_factory():
    """Session factory handed to background tasks, which must open their own
    session after the request that scheduled them has already returned.
    Overridden in tests so background work lands in the same test database.
    """
    return SessionLocal
