from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import httpx

from skillproof.config import get_settings


class GitHubAuthError(Exception):
    """Raised when a stored GitHub token has been revoked or is invalid."""


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str


@dataclass(frozen=True)
class Repo:
    owner: str
    name: str
    fork: bool = False

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class CommitRecord:
    repo: Repo
    sha: str
    message: str
    date: datetime
    files: list[str]
    diff_text: str
    url: str


@dataclass(frozen=True)
class PrCommentRecord:
    repo: Repo
    comment_id: int
    body: str
    date: datetime
    url: str


class GitHubClient(ABC):
    """Everything the app needs from GitHub, as one seam.

    Real network access happens only in `RealGitHubClient`. Tests substitute
    `FakeGitHubClient` with canned fixture data so scoring stays deterministic.
    """

    @abstractmethod
    def exchange_code_for_token(self, code: str) -> str: ...

    @abstractmethod
    def get_authenticated_user(self, token: str) -> GitHubUser: ...

    @abstractmethod
    def list_owned_public_repos(self, token: str, login: str) -> list[Repo]: ...

    @abstractmethod
    def list_external_repos_with_merged_prs(self, token: str, login: str) -> list[Repo]: ...

    @abstractmethod
    def list_commits(self, token: str, repo: Repo, author_login: str) -> list[CommitRecord]: ...

    @abstractmethod
    def list_pr_review_comments(self, token: str, repo: Repo, author_login: str) -> list[PrCommentRecord]: ...


class RealGitHubClient(GitHubClient):
    """Talks to api.github.com over HTTPS, read-only, public data only."""

    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        settings = get_settings()
        self._client_id = client_id or settings.github_client_id
        self._client_secret = client_secret or settings.github_client_secret
        self._etag_cache: dict[str, tuple[str, object]] = {}

    def exchange_code_for_token(self, code: str) -> str:
        settings = get_settings()
        response = httpx.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise GitHubAuthError(f"GitHub OAuth exchange failed: {payload}")
        return token

    def get_authenticated_user(self, token: str) -> GitHubUser:
        data = self._get_json(token, "/user")
        return GitHubUser(id=data["id"], login=data["login"])

    def list_owned_public_repos(self, token: str, login: str) -> list[Repo]:
        data = self._get_json(token, f"/users/{login}/repos", params={"type": "owner", "per_page": 100})
        return [Repo(owner=r["owner"]["login"], name=r["name"], fork=r["fork"]) for r in data if not r["fork"]]

    def list_external_repos_with_merged_prs(self, token: str, login: str) -> list[Repo]:
        data = self._get_json(
            token,
            "/search/issues",
            params={"q": f"author:{login} type:pr is:merged", "per_page": 100},
        )
        seen: dict[str, Repo] = {}
        for item in data.get("items", []):
            owner, name = _owner_and_name_from_repo_url(item["repository_url"])
            if owner.lower() == login.lower():
                continue
            seen[f"{owner}/{name}"] = Repo(owner=owner, name=name, fork=False)
        return list(seen.values())

    def list_commits(self, token: str, repo: Repo, author_login: str) -> list[CommitRecord]:
        commits = self._get_json(
            token,
            f"/repos/{repo.full_name}/commits",
            params={"author": author_login, "per_page": 100},
        )
        records = []
        for c in commits:
            detail = self._get_json(token, f"/repos/{repo.full_name}/commits/{c['sha']}")
            files = [f["filename"] for f in detail.get("files", [])]
            diff_text = "\n".join(f.get("patch", "") for f in detail.get("files", []) if f.get("patch"))
            records.append(
                CommitRecord(
                    repo=repo,
                    sha=c["sha"],
                    message=detail["commit"]["message"],
                    date=_parse_date(detail["commit"]["author"]["date"]),
                    files=files,
                    diff_text=diff_text,
                    url=detail["html_url"],
                )
            )
        return records

    def list_pr_review_comments(self, token: str, repo: Repo, author_login: str) -> list[PrCommentRecord]:
        data = self._get_json(token, f"/repos/{repo.full_name}/pulls/comments", params={"per_page": 100})
        return [
            PrCommentRecord(
                repo=repo,
                comment_id=c["id"],
                body=c["body"],
                date=_parse_date(c["created_at"]),
                url=c["html_url"],
            )
            for c in data
            if c.get("user", {}).get("login", "").lower() == author_login.lower()
        ]

    def _get_json(self, token: str, path: str, params: dict | None = None, max_retries: int = 5):
        url = f"https://api.github.com{path}"
        cache_key = f"{url}?{params}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        cached_etag, cached_body = self._etag_cache.get(cache_key, (None, None))
        if cached_etag:
            headers["If-None-Match"] = cached_etag

        attempt = 0
        while True:
            response = httpx.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 304 and cached_body is not None:
                return cached_body
            if response.status_code == 401:
                raise GitHubAuthError("GitHub token is invalid or has been revoked")
            if response.status_code == 403 and _is_secondary_rate_limit(response) and attempt < max_retries:
                time.sleep(_backoff_seconds(response, attempt))
                attempt += 1
                continue
            response.raise_for_status()
            body = response.json()
            etag = response.headers.get("ETag")
            if etag:
                self._etag_cache[cache_key] = (etag, body)
            return body


def _is_secondary_rate_limit(response: httpx.Response) -> bool:
    if response.headers.get("Retry-After"):
        return True
    body_text = response.text.lower()
    return "secondary rate limit" in body_text or "abuse detection" in body_text


def _backoff_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        return float(retry_after)
    return min(2**attempt, 60)


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _owner_and_name_from_repo_url(repository_url: str) -> tuple[str, str]:
    """GitHub search results give a repo as an API URL, e.g.
    'https://api.github.com/repos/{owner}/{name}' — the path's last two
    segments are always owner and name, regardless of host/scheme.
    """
    owner, name = urlparse(repository_url).path.rstrip("/").split("/")[-2:]
    return owner, name


@dataclass
class FakeGitHubClient(GitHubClient):
    """Fixture-backed double for tests: canned repos/commits/PRs, no network."""

    users_by_code: dict[str, GitHubUser] = field(default_factory=dict)
    tokens_by_code: dict[str, str] = field(default_factory=dict)
    owned_repos: dict[str, list[Repo]] = field(default_factory=dict)
    external_repos: dict[str, list[Repo]] = field(default_factory=dict)
    commits: dict[str, list[CommitRecord]] = field(default_factory=dict)
    pr_comments: dict[str, list[PrCommentRecord]] = field(default_factory=dict)
    revoked_tokens: set[str] = field(default_factory=set)

    def exchange_code_for_token(self, code: str) -> str:
        return self.tokens_by_code.get(code, f"fake-token-for-{code}")

    def get_authenticated_user(self, token: str) -> GitHubUser:
        self._check_token(token)
        for code, user in self.users_by_code.items():
            if self.tokens_by_code.get(code, f"fake-token-for-{code}") == token:
                return user
        return GitHubUser(id=hash(token) % 1_000_000, login=f"user-{token[:8]}")

    def list_owned_public_repos(self, token: str, login: str) -> list[Repo]:
        self._check_token(token)
        return self.owned_repos.get(login, [])

    def list_external_repos_with_merged_prs(self, token: str, login: str) -> list[Repo]:
        self._check_token(token)
        return self.external_repos.get(login, [])

    def list_commits(self, token: str, repo: Repo, author_login: str) -> list[CommitRecord]:
        self._check_token(token)
        return self.commits.get(repo.full_name, [])

    def list_pr_review_comments(self, token: str, repo: Repo, author_login: str) -> list[PrCommentRecord]:
        self._check_token(token)
        return self.pr_comments.get(repo.full_name, [])

    def _check_token(self, token: str) -> None:
        if token in self.revoked_tokens:
            raise GitHubAuthError("GitHub token is invalid or has been revoked")
