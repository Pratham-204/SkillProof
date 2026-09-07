from __future__ import annotations

import base64
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar
from urllib.parse import urlparse

import httpx

from skillproof.config import get_settings

logger = logging.getLogger(__name__)

# Statuses that mean "this specific repo/PR/file is gone or unreachable to us
# right now" rather than a systemic problem — safe to skip just that one
# resource's evidence rather than letting the exception propagate. A repo
# found via list_merged_prs's search index can be deleted, renamed,
# transferred, made private, or have the candidate's access revoked by the
# time a later per-repo call reaches it; that must not abort every other
# repo's already-gathered evidence for the whole /verify run. 429 is included
# because a still-rate-limited resource after _fetch_page's retries exhaust
# raises exactly this status — that must degrade to "skip this one resource"
# too, not crash the whole run. Anything else (5xx, network errors) still
# propagates — those are more likely transient or systemic and worth
# surfacing rather than silently swallowing.
_SKIPPABLE_STATUSES = frozenset({404, 403, 429})


def _skip_reason(exc: httpx.HTTPStatusError) -> str:
    """A 429 reaching one of _SKIPPABLE_STATUSES's call sites was NOT
    necessarily confirmed as a rate limit — _is_rate_limited only gates
    whether _fetch_page's retry loop engages at all; a 429 with no rate-limit
    signal (no Retry-After, X-RateLimit-Remaining not "0") skips the retry
    loop entirely and raises immediately, indistinguishable by status code
    alone from a rate-limited 429 that exhausted every retry. Both still get
    treated as skippable (the alternative — crashing the whole run over an
    ambiguous 429 — is worse), but the log should say which case it was
    rather than implying every 429 here was confirmed rate-limiting."""
    status = exc.response.status_code
    if status != 429:
        return str(status)
    if _is_rate_limited(exc.response):
        return "429 (rate-limited; retries exhausted)"
    return "429 (no rate-limit signal present — treated as skippable, but not confirmed to be rate-limiting)"

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


_T = TypeVar("_T")
_R = TypeVar("_R")


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
    # Threaded through to EvidenceItem/QualifyingEvidence so a public Evidence
    # Card can redact which private repo backed a piece of evidence instead of
    # exposing it to anyone with the card's URL. Defaults False so every
    # existing external/fixture Repo — which was always public before private
    # repos existed at all — is unaffected.
    private: bool = False

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
    def list_owned_repos(self, token: str, login: str) -> list[Repo]:
        """The Candidate's owned, non-fork repos — private ones included when the
        token's OAuth scope allows it, falling back to public-only otherwise
        (`RealGitHubClient`'s own docstring covers exactly how)."""
        ...

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

    def list_qualifying_commits(
        self, token: str, login: str, on_repo_scanned: Callable[[str], None] | None = None
    ) -> list[CommitRecord]:
        """The Candidate's Volume-qualifying commits (ADR-0004): every author-matching
        commit in their owned, non-fork repos, plus — for repos they don't own — only
        commits that are part of a PR they actually opened and had merged there. This
        orchestration (which repos are owned vs. external, and which fetch strategy
        applies to each) lives here, once, rather than in the caller or duplicated per
        adapter, so there's no method left to call that would let an external repo's
        unscoped commit history count. Adapters only implement the two fetch hooks below.

        Each repo's commits are gathered via `_map_repos` (github-scan-performance
        ticket 03), which defaults to sequential but lets `RealGitHubClient` fetch
        multiple repos concurrently without this orchestration knowing or caring.

        `on_repo_scanned`, if given, is called once per unique repo (owned or
        external) right after that repo's commits have been gathered — real,
        already-happened per-repo progress for the verify SSE stream (ticket 03),
        not a fabricated signal. A repo with more than one merged PR is only
        announced once, on first encounter. Announcing is guarded by a lock since
        `_map_repos` may call this from more than one thread concurrently.
        """
        owned_repos = self.list_owned_repos(token, login)
        merged_prs = self.list_merged_prs(token, login)

        commits: list[CommitRecord] = []
        seen: set[tuple[str, str]] = set()
        announced: set[str] = set()
        announce_lock = threading.Lock()

        def _announce(repo: Repo) -> None:
            if on_repo_scanned is None:
                return
            with announce_lock:
                if repo.full_name in announced:
                    return
                announced.add(repo.full_name)
            on_repo_scanned(repo.full_name)

        def _owned_task(repo: Repo) -> list[CommitRecord]:
            result = self._fetch_owned_commits(token, repo, login)
            _announce(repo)
            return result

        def _pr_task(pr: MergedPullRequest) -> list[CommitRecord]:
            result = self._fetch_pr_commits(token, pr.repo, pr.number)
            _announce(pr.repo)
            return result

        for result in self._map_repos(_owned_task, owned_repos):
            for commit in result:
                _append_unique(commits, seen, commit)
        for result in self._map_repos(_pr_task, merged_prs):
            for commit in result:
                _append_unique(commits, seen, commit)
        return commits

    def _map_repos(self, fn: Callable[[_T], _R], items: Iterable[_T]) -> list[_R]:
        """Runs `fn` once per item, in order. Sequential by default (used as-is by
        `FakeGitHubClient`, where fixture reads are instant); `RealGitHubClient`
        overrides this to fan the calls out across its own repo-level thread pool,
        since that's the only adapter where per-repo network latency is worth
        overlapping (github-scan-performance ticket 03)."""
        return [fn(item) for item in items]

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
        self._etag_cache: dict[str, tuple[str, object, dict]] = {}
        self._etag_lock = threading.Lock()
        # follow_redirects: a renamed/transferred repo answers at its old path with
        # a 301/302 instead of the resource. Without this, raise_for_status() (which
        # doesn't fire for a 3xx) lets the tiny redirect payload through as if it
        # were real data. GitHub's redirects are same-origin with the same auth
        # semantics, so following them is safe.
        self._client = httpx.Client(transport=transport, timeout=15, follow_redirects=True)

        # Shared for this client's whole lifetime (github-scan-performance
        # tickets 01/03), not recreated per call — and note `deps.get_github_client`
        # makes `RealGitHubClient` a process-wide `@lru_cache` singleton, so
        # that lifetime is the whole app process, not just one scan. Two
        # separate pools rather than one: `_repo_pool`'s
        # workers call back into methods (`_fetch_owned_commits` etc.) that
        # themselves submit to `_item_pool` and wait on the result — submitting
        # that inner work to the *same* bounded pool the outer task is running in
        # would starve it (every worker blocked waiting on a queued task no
        # worker is free to run). Distinct pools with no cycle between them can't
        # deadlock that way.
        self._item_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="github-item")
        self._repo_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="github-repo")

        # A shared cooldown (ticket 02, hardened after a real incident): every
        # thread checks `_rate_limited_until` before issuing a request and waits
        # if it's still in the future, and a thread that discovers a new rate
        # limit extends it (never shortens it — `max()`) for every other thread
        # to see. This is what makes N concurrently-rate-limited threads (e.g.
        # `_item_pool`'s 8 workers hitting the same token's limit at once)
        # collapse into roughly ONE wait instead of each independently
        # rediscovering the same 403 and separately retrying up to
        # `max_retries` times — which, unguarded, serialized into an aggregate
        # wait of (worker count) * max_retries * (per-attempt cap), not the
        # single-thread bound the per-attempt cap alone would suggest.
        self._rate_limit_gate = threading.Lock()
        self._rate_limited_until = 0.0

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

    def list_owned_repos(self, token: str, login: str) -> list[Repo]:
        """`/user/repos` (authenticated) sees exactly what the token's OAuth scope
        allows — private repos too, once that scope includes `repo` (settings.
        github_oauth_scope). `visibility`/`affiliation` and the old endpoint's
        `type` param are mutually exclusive on GitHub's side, so this doesn't
        reuse that param name even though it means the same thing.

        A Candidate who connected before private-repo support existed carries a
        token issued under the old, narrower scope and hasn't necessarily
        reconnected — GitHub responds to that gap with a 404/403 on this
        endpoint rather than silently omitting private repos, so this falls
        back to the original public-only listing (`/users/{login}/repos`,
        which works for any token regardless of scope) rather than failing
        the whole scan over a capability this token simply doesn't have.
        """
        try:
            data = self._get_all_pages(
                token, "/user/repos", params={"visibility": "all", "affiliation": "owner", "per_page": 100}
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # A scope-denial fails immediately on page 1 — never mid-pagination on
            # page 2+, which is far more likely a transient error (502/504, a
            # primary rate limit) that must propagate rather than silently
            # downgrade a candidate with private repos to a public-only result.
            is_first_page = exc.response.request.url.params.get("page") in (None, "1")
            if status not in (403, 404) or not is_first_page:
                raise
            logger.warning(
                "Falling back to public-only repo listing for %s: /user/repos returned %s on the first page",
                login,
                status,
            )
            data = self._get_all_pages(token, f"/users/{login}/repos", params={"type": "owner", "per_page": 100})
            return [Repo(owner=r["owner"]["login"], name=r["name"], fork=r["fork"]) for r in data if not r["fork"]]
        return [
            Repo(owner=r["owner"]["login"], name=r["name"], fork=r["fork"], private=r["private"])
            for r in data
            if not r["fork"]
        ]

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
        try:
            commits = self._get_all_pages(
                token,
                f"/repos/{repo.full_name}/commits",
                params={"author": author_login, "per_page": 100},
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 409:
                # GitHub returns 409 Conflict from this endpoint for a repo with no
                # commits yet (empty repo, no default branch) — zero commits, not an error.
                return []
            if status in _SKIPPABLE_STATUSES:
                # The repo was listed by list_owned_repos moments ago but is gone,
                # renamed, or now inaccessible by the time this call runs — skip
                # just this repo's commits rather than aborting the whole scan.
                logger.warning("Skipping owned repo %s: commits fetch returned %s", repo.full_name, _skip_reason(exc))
                return []
            raise
        return self._commit_records(token, repo, [c["sha"] for c in commits])

    def _fetch_pr_commits(self, token: str, repo: Repo, pr_number: int) -> list[CommitRecord]:
        try:
            commits = self._get_all_pages(
                token, f"/repos/{repo.full_name}/pulls/{pr_number}/commits", params={"per_page": 100}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in _SKIPPABLE_STATUSES:
                # list_merged_prs found this PR via GitHub's search index, which
                # lags reality — the repo can be deleted, renamed, transferred, or
                # made private by the time this per-PR call runs. Skip just this
                # PR's commits rather than aborting the whole scan.
                logger.warning(
                    "Skipping merged PR #%s in %s: commits fetch returned %s",
                    pr_number,
                    repo.full_name,
                    _skip_reason(exc),
                )
                return []
            raise
        return self._commit_records(token, repo, [c["sha"] for c in commits])

    def _commit_records(self, token: str, repo: Repo, shas: list[str]) -> list[CommitRecord]:
        """Fetches every commit's diff concurrently instead of one at a time
        (github-scan-performance ticket 01) — this was the dominant N+1 cost in a
        scan, one extra request per commit. Futures are built and gathered in
        `shas` order, so the result order is unchanged even though completion
        order isn't."""
        if not shas:
            return []
        futures = [self._item_pool.submit(self._commit_record, token, repo, sha) for sha in shas]
        return [future.result() for future in futures]

    def _commit_record(self, token: str, repo: Repo, sha: str) -> CommitRecord:
        detail = self._get_json(token, f"/repos/{repo.full_name}/commits/{sha}")
        files_data = detail.get("files", [])
        if len(files_data) == 300:
            # This endpoint's "files" array paginates past 300 entries via Link
            # headers that _get_json never follows — 300 exactly is the strong
            # signal of truncation (GitHub always caps at exactly 300 per page).
            logger.warning("Commit %s in %s has exactly 300 files; files/diff may be truncated", sha, repo.full_name)
        files = [f["filename"] for f in files_data]
        diff_text = "\n".join(f.get("patch", "") for f in files_data if f.get("patch"))
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
        try:
            data = self._get_all_pages(token, f"/repos/{repo.full_name}/pulls/comments", params={"per_page": 100})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in _SKIPPABLE_STATUSES:
                # Same stale-search-hit gap as _fetch_pr_commits above: skip this
                # repo's PR comments rather than aborting the whole scan.
                logger.warning(
                    "Skipping PR review comments for %s: fetch returned %s", repo.full_name, _skip_reason(exc)
                )
                return []
            raise
        return [
            PrCommentRecord(
                repo=repo,
                comment_id=c["id"],
                body=c["body"],
                date=_parse_date(c["created_at"]),
                url=c["html_url"],
            )
            for c in data
            if (c.get("user") or {}).get("login", "").lower() == author_login.lower()
        ]

    def get_manifest_files(self, token: str, repo: Repo) -> dict[str, str]:
        """Checks all `MANIFEST_FILENAMES` concurrently instead of one at a time
        (github-scan-performance ticket 01) — this was up to 20 sequential
        requests per repo just to detect which manifests exist."""

        def _fetch_one(filename: str) -> tuple[str, str | None]:
            try:
                data = self._get_json(token, f"/repos/{repo.full_name}/contents/{filename}")
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 404:
                    # The file doesn't exist at this path — an expected, silent
                    # outcome for most of MANIFEST_FILENAMES on any given repo.
                    return filename, None
                if status in _SKIPPABLE_STATUSES:
                    # Repo became inaccessible (deleted/private/access-revoked)
                    # between being listed and this call — skip just this
                    # filename rather than aborting the whole repo's manifest
                    # check (and, upstream, the entire scan).
                    logger.warning(
                        "Skipping manifest file %s in %s: fetch returned %s", filename, repo.full_name, _skip_reason(exc)
                    )
                    return filename, None
                raise
            content = data.get("content") if isinstance(data, dict) else None
            if not content:
                return filename, None
            return filename, base64.b64decode(content).decode("utf-8", errors="replace")

        futures = [self._item_pool.submit(_fetch_one, filename) for filename in MANIFEST_FILENAMES]
        result: dict[str, str] = {}
        for future in futures:
            filename, content = future.result()
            if content is not None:
                result[filename] = content
        return result

    def _map_repos(self, fn: Callable[[_T], _R], items: Iterable[_T]) -> list[_R]:
        """Fans repos out across the shared repo-level pool (ticket 03) instead of
        finishing one repo's commits before starting the next. Uses its own pool,
        separate from `_item_pool`, so `fn` (which itself submits per-commit work
        to `_item_pool` and waits) can't deadlock waiting on a pool its own
        worker thread occupies."""
        items = list(items)
        if not items:
            return []
        futures = [self._repo_pool.submit(fn, item) for item in items]
        return [future.result() for future in futures]

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
        same defensive bound `_fetch_page`'s own retry loop already applies — but a
        legitimately larger result set (e.g. list_pr_review_comments on a repo with
        10,000+ comments, or an owned repo with 10,000+ commits) hits it too, so
        exhausting it is logged rather than silently truncating every such caller.
        """
        url: str | None = f"https://api.github.com{path}"
        results: list = []
        for _ in range(max_pages):
            if url is None:
                break
            body, links = self._fetch_page(token, url, params)
            results.extend(body["items"] if isinstance(body, dict) else body)
            url = links.get("next", {}).get("url")
            params = None  # the next-page URL already carries the full query string
        if url is not None:
            logger.warning("Pagination stopped after max_pages=%s for %s; results are truncated", max_pages, path)
        return results

    def _fetch_page(self, token: str, url: str, params: dict | None, max_retries: int = 5):
        """One page: handles auth errors, rate-limit backoff, and ETag caching.
        Returns `(body, links)` — `links` is `response.links`-shaped (e.g.
        `links["next"]["url"]`), the next-page Link header info `_get_all_pages`
        needs, sourced from the cache on a 304 since GitHub doesn't necessarily
        repeat the original 200's Link header on a not-modified response.

        Runs concurrently from multiple threads once a scan is parallelized
        (tickets 01/03), so both the ETag cache and rate-limit backoff below are
        shared, locked state rather than assuming single-threaded access.
        """
        cache_key = f"{url}?{params}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        with self._etag_lock:
            cached_etag, cached_body, cached_links = self._etag_cache.get(cache_key, (None, None, None))
        if cached_etag:
            headers["If-None-Match"] = cached_etag

        attempt = 0
        while True:
            # Wait out whatever cooldown any thread (this one or another) has
            # already discovered, sourced from the shared timestamp rather than
            # rediscovering it via a fresh 403/429 of our own — this is what
            # collapses N concurrently-rate-limited threads into roughly one
            # wait instead of each independently retrying up to max_retries times.
            with self._rate_limit_gate:
                remaining = self._rate_limited_until - time.time()
            if remaining > 0:
                time.sleep(remaining)
            response = self._client.get(url, headers=headers, params=params)
            if response.status_code == 304 and cached_body is not None:
                return cached_body, cached_links or {}
            if response.status_code == 401:
                raise GitHubAuthError("GitHub token is invalid or has been revoked")
            if response.status_code in (403, 429) and _is_rate_limited(response) and attempt < max_retries:
                wait_for = _backoff_seconds(response, attempt)
                with self._rate_limit_gate:
                    # max(), never overwrite: two threads discovering the same
                    # limit near-simultaneously must not let the later one's
                    # (possibly shorter, due to clock/response timing) estimate
                    # shorten a wait another thread is already relying on.
                    self._rate_limited_until = max(self._rate_limited_until, time.time() + wait_for)
                attempt += 1
                continue
            response.raise_for_status()
            body = response.json()
            etag = response.headers.get("ETag")
            if etag:
                with self._etag_lock:
                    self._etag_cache[cache_key] = (etag, body, response.links)
            return body, response.links


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


def _is_primary_rate_limit(response: httpx.Response) -> bool:
    # GitHub's primary limit (5000 req/hr authenticated) carries neither a
    # Retry-After header nor "secondary rate limit"/"abuse detection" body text —
    # this is the only signal that distinguishes it from a genuine 403/429.
    return response.headers.get("X-RateLimit-Remaining") == "0"


def _is_rate_limited(response: httpx.Response) -> bool:
    return _is_secondary_rate_limit(response) or _is_primary_rate_limit(response)


_MAX_BACKOFF_SECONDS = 60.0  # every branch below is capped at this — see the incident note below


def _backoff_seconds(response: httpx.Response, attempt: int) -> float:
    """Every branch here is capped at _MAX_BACKOFF_SECONDS and never raises,
    however malformed the response's headers are. Both properties are
    load-bearing: this value feeds a real sleep (via the shared
    _rate_limited_until timestamp in _fetch_page) that every GitHub request
    across the whole process waits on, since RealGitHubClient is a
    process-wide singleton — an uncapped or exception-raising value here was
    a real production incident (one candidate's rate limit froze GitHub
    connectivity for every concurrent scan on the server, for up to an hour,
    the first time; a second, still-uncapped branch reproduced the same
    freeze through GitHub's secondary/abuse-detection path, which this fixes
    too). If the limit genuinely hasn't cleared after max_retries's worth of
    capped waits, the caller gives up and the request's status is handled
    like any other failure — skipped per-repo (_SKIPPABLE_STATUSES) rather
    than hanging.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), _MAX_BACKOFF_SECONDS)
        except ValueError:
            pass  # non-numeric Retry-After (a malformed/unexpected value) — fall through
    reset_at = response.headers.get("X-RateLimit-Reset")
    if reset_at and _is_primary_rate_limit(response):
        try:
            return min(max(float(reset_at) - time.time(), 1.0), _MAX_BACKOFF_SECONDS)
        except ValueError:
            pass  # non-numeric X-RateLimit-Reset — fall through to the exponential default
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
    invalid_codes: set[str] = field(default_factory=set)

    def exchange_code_for_token(self, code: str) -> str:
        if code in self.invalid_codes:
            # Simulates GitHub rejecting an already-consumed or expired OAuth
            # `code` (a double-submitted /callback), the same failure a real
            # GitHubAuthError from RealGitHubClient.exchange_code_for_token
            # would raise.
            raise GitHubAuthError("GitHub OAuth code is invalid or has already been used")
        return self.tokens_by_code.get(code, f"fake-token-for-{code}")

    def get_authenticated_user(self, token: str) -> GitHubUser:
        self._check_token(token)
        for code, user in self.users_by_code.items():
            if self.tokens_by_code.get(code, f"fake-token-for-{code}") == token:
                return user
        return GitHubUser(id=hash(token) % 1_000_000, login=f"user-{token[:8]}")

    def list_owned_repos(self, token: str, login: str) -> list[Repo]:
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
