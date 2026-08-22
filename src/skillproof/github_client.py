from __future__ import annotations

import base64
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import httpx

from skillproof.config import get_settings

# The well-known dependency-manifest filenames Presence checks against,
# fetched once per repo (issue 02) rather than once per claimed skill.
MANIFEST_FILENAMES = (
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "Pipfile",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "mix.exs",
    "pubspec.yaml",
    "Package.swift",
    "project.clj",
    "deps.edn",
    "rebar.config",
    "stack.yaml",
    "Project.toml",
)


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


@dataclass(frozen=True)
class MergedPullRequest:
    """One PR the Candidate opened and had merged in an external (non-owned) repo.

    Volume for external repos is scoped to exactly these PRs' own commits
    (hybrid-scoring ticket 03) — never a blanket author-filtered scan of the
    repo's full history, which a forked repo would trivially satisfy with someone else's work.
    """

    repo: Repo
    number: int


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
    def list_merged_prs(self, token: str, login: str) -> list[MergedPullRequest]:
        """Every PR the Candidate opened and had merged in a repo they don't own."""
        ...

    @abstractmethod
    def list_pr_review_comments(self, token: str, repo: Repo, author_login: str) -> list[PrCommentRecord]: ...

    @abstractmethod
    def get_manifest_files(self, token: str, repo: Repo) -> dict[str, str]:
        """Contents of whichever `MANIFEST_FILENAMES` exist in `repo`'s default branch,
        keyed by filename. Missing files are simply absent from the result, not an error."""
        ...

    def list_qualifying_commits(self, token: str, login: str) -> list[CommitRecord]:
        """The Candidate's Volume-qualifying commits (ADR-0004): every author-matching
        commit in their owned, non-fork repos, plus — for repos they don't own — only
        commits that are part of a PR they actually opened and had merged there. This
        orchestration (which repos are owned vs. external, and which fetch strategy
        applies to each) lives here, once, rather than in the caller or duplicated per
        adapter, so there's no method left to call that would let an external repo's
        unscoped commit history count. Adapters only implement the two fetch hooks below.
        """
        owned_repos = self.list_owned_public_repos(token, login)
        merged_prs = self.list_merged_prs(token, login)

        commits: list[CommitRecord] = []
        seen: set[tuple[str, str]] = set()
        for repo in owned_repos:
            for commit in self._fetch_owned_commits(token, repo, login):
                _append_unique(commits, seen, commit)
        for pr in merged_prs:
            for commit in self._fetch_pr_commits(token, pr.repo, pr.number):
                _append_unique(commits, seen, commit)
        return commits

    @abstractmethod
    def _fetch_owned_commits(self, token: str, repo: Repo, author_login: str) -> list[CommitRecord]:
        """Every author-matching commit in one owned, non-fork repo."""
        ...

    @abstractmethod
    def _fetch_pr_commits(self, token: str, repo: Repo, pr_number: int) -> list[CommitRecord]:
        """Commits belonging to one specific (merged) PR, for external-repo Volume scoping."""
        ...


class RealGitHubClient(GitHubClient):
    """Talks to api.github.com over HTTPS, read-only, public data only."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        """`transport` is the test seam: pass `httpx.MockTransport(handler)` to drive
        this client without a real network call. Left unset, httpx uses its normal
        transport, so production behavior is unaffected.
        """
        settings = get_settings()
        self._client_id = client_id or settings.github_client_id
        self._client_secret = client_secret or settings.github_client_secret
        self._etag_cache: dict[str, tuple[str, object]] = {}
        self._client = httpx.Client(transport=transport, timeout=15)

    def exchange_code_for_token(self, code: str) -> str:
        settings = get_settings()
        response = self._client.post(
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
        data = self._get_all_pages(token, f"/users/{login}/repos", params={"type": "owner", "per_page": 100})
        return [Repo(owner=r["owner"]["login"], name=r["name"], fork=r["fork"]) for r in data if not r["fork"]]

    def list_merged_prs(self, token: str, login: str) -> list[MergedPullRequest]:
        data = self._get_all_pages(
            token,
            "/search/issues",
            params={"q": f"author:{login} type:pr is:merged", "per_page": 100},
        )
        results = []
        for item in data:
            owner, name = _owner_and_name_from_repo_url(item["repository_url"])
            if owner.lower() == login.lower():
                continue
            results.append(MergedPullRequest(repo=Repo(owner=owner, name=name, fork=False), number=item["number"]))
        return results

    def _fetch_owned_commits(self, token: str, repo: Repo, author_login: str) -> list[CommitRecord]:
        commits = self._get_all_pages(
            token,
            f"/repos/{repo.full_name}/commits",
            params={"author": author_login, "per_page": 100},
        )
        return [self._commit_record(token, repo, c["sha"]) for c in commits]

    def _fetch_pr_commits(self, token: str, repo: Repo, pr_number: int) -> list[CommitRecord]:
        commits = self._get_all_pages(
            token, f"/repos/{repo.full_name}/pulls/{pr_number}/commits", params={"per_page": 100}
        )
        return [self._commit_record(token, repo, c["sha"]) for c in commits]

    def _commit_record(self, token: str, repo: Repo, sha: str) -> CommitRecord:
        detail = self._get_json(token, f"/repos/{repo.full_name}/commits/{sha}")
        files = [f["filename"] for f in detail.get("files", [])]
        diff_text = "\n".join(f.get("patch", "") for f in detail.get("files", []) if f.get("patch"))
        return CommitRecord(
            repo=repo,
            sha=sha,
            message=detail["commit"]["message"],
            date=_parse_date(detail["commit"]["author"]["date"]),
            files=files,
            diff_text=diff_text,
            url=detail["html_url"],
        )

    def list_pr_review_comments(self, token: str, repo: Repo, author_login: str) -> list[PrCommentRecord]:
        data = self._get_all_pages(token, f"/repos/{repo.full_name}/pulls/comments", params={"per_page": 100})
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

    def get_manifest_files(self, token: str, repo: Repo) -> dict[str, str]:
        result: dict[str, str] = {}
        for filename in MANIFEST_FILENAMES:
            try:
                data = self._get_json(token, f"/repos/{repo.full_name}/contents/{filename}")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    continue
                raise
            content = data.get("content") if isinstance(data, dict) else None
            if content:
                result[filename] = base64.b64decode(content).decode("utf-8", errors="replace")
        return result

    def _get_json(self, token: str, path: str, params: dict | None = None):
        """One single-object response — `/user`, a commit's detail, a manifest file.
        Never paginated; see `_get_all_pages` for list-shaped endpoints."""
        body, _ = self._fetch_page(token, f"https://api.github.com{path}", params)
        return body

    def _get_all_pages(self, token: str, path: str, params: dict | None = None, max_pages: int = 100) -> list:
        """Follows the response's `Link: rel="next"` header until exhausted, so a
        result set bigger than one `per_page=100` page is never silently truncated —
        the bug this method replaces. Handles both a bare JSON array and the GitHub
        search API's `{"items": [...]}` shape, flattening either into one list.
        `max_pages` is a safety net against a malformed/cyclical Link header, the
        same defensive bound `_fetch_page`'s own retry loop already applies.
        """
        url: str | None = f"https://api.github.com{path}"
        results: list = []
        for _ in range(max_pages):
            if url is None:
                break
            body, response = self._fetch_page(token, url, params)
            results.extend(body["items"] if isinstance(body, dict) else body)
            url = response.links.get("next", {}).get("url")
            params = None  # the next-page URL already carries the full query string
        return results

    def _fetch_page(self, token: str, url: str, params: dict | None, max_retries: int = 5):
        """One page: handles auth errors, secondary-rate-limit backoff, and ETag
        caching. Returns `(body, response)` — callers needing the next-page Link
        header (`_get_all_pages`) read it off `response.links`."""
        cache_key = f"{url}?{params}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        cached_etag, cached_body = self._etag_cache.get(cache_key, (None, None))
        if cached_etag:
            headers["If-None-Match"] = cached_etag

        attempt = 0
        while True:
            response = self._client.get(url, headers=headers, params=params)
            if response.status_code == 304 and cached_body is not None:
                return cached_body, response
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
            return body, response


def _append_unique(commits: list[CommitRecord], seen: set[tuple[str, str]], commit: CommitRecord) -> None:
    """A commit can appear in more than one of a Candidate's merged PRs in the same
    repo (e.g. a shared base commit) — it must only count once toward Volume."""
    key = (commit.repo.full_name, commit.sha)
    if key in seen:
        return
    seen.add(key)
    commits.append(commit)


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
    merged_prs: dict[str, list[MergedPullRequest]] = field(default_factory=dict)
    commits: dict[str, list[CommitRecord]] = field(default_factory=dict)
    pr_commits: dict[tuple[str, int], list[CommitRecord]] = field(default_factory=dict)
    pr_comments: dict[str, list[PrCommentRecord]] = field(default_factory=dict)
    manifest_files: dict[str, dict[str, str]] = field(default_factory=dict)
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

    def list_merged_prs(self, token: str, login: str) -> list[MergedPullRequest]:
        self._check_token(token)
        return self.merged_prs.get(login, [])

    def _fetch_owned_commits(self, token: str, repo: Repo, author_login: str) -> list[CommitRecord]:
        self._check_token(token)
        return self.commits.get(repo.full_name, [])

    def _fetch_pr_commits(self, token: str, repo: Repo, pr_number: int) -> list[CommitRecord]:
        self._check_token(token)
        return self.pr_commits.get((repo.full_name, pr_number), [])

    def list_pr_review_comments(self, token: str, repo: Repo, author_login: str) -> list[PrCommentRecord]:
        self._check_token(token)
        return self.pr_comments.get(repo.full_name, [])

    def get_manifest_files(self, token: str, repo: Repo) -> dict[str, str]:
        self._check_token(token)
        return self.manifest_files.get(repo.full_name, {})

    def _check_token(self, token: str) -> None:
        if token in self.revoked_tokens:
            raise GitHubAuthError("GitHub token is invalid or has been revoked")
