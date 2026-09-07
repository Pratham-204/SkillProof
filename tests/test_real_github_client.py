"""RealGitHubClient previously had zero test coverage and no pagination
handling despite every list-fetching call passing per_page=100 — a Candidate
with more than 100 commits/PRs/comments in one repo had Volume (the
highest-weighted signal) silently truncated at page 1.

RealGitHubClient now accepts an injectable httpx transport (defaulting to a
real network transport), so these tests drive it directly with
`httpx.MockTransport` — no new test dependency, httpx ships this itself.
"""

import base64
import logging
import threading
import time

import httpx
import pytest

from skillproof import github_client, security, verify_service
from skillproof.github_client import GitHubAuthError, RealGitHubClient, Repo
from skillproof.models import Candidate, EvidenceCard


def _client(handler) -> RealGitHubClient:
    return RealGitHubClient(client_id="id", client_secret="secret", transport=httpx.MockTransport(handler))


class _ConcurrencyTracker:
    """Records the peak number of overlapping in-flight requests a MockTransport
    handler sees, so a test can prove requests actually ran concurrently rather
    than merely returning correct results one at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self._current += 1
            self.peak = max(self.peak, self._current)

    def exit(self) -> None:
        with self._lock:
            self._current -= 1


def test_list_owned_repos_follows_link_header_pagination():
    """A plain-array endpoint (repos) spanning two pages must not be truncated
    at page 1 — this is the exact silent-truncation bug candidate 2 flagged."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200, json=[{"owner": {"login": "octodev"}, "name": "repo-b", "fork": False, "private": False}]
            )
        return httpx.Response(
            200,
            json=[{"owner": {"login": "octodev"}, "name": "repo-a", "fork": False, "private": False}],
            headers={"Link": '<https://api.github.com/user/repos?affiliation=owner&per_page=100&page=2>; rel="next"'},
        )

    client = _client(handler)

    repos = client.list_owned_repos("token", "octodev")

    assert {r.name for r in repos} == {"repo-a", "repo-b"}


def test_list_owned_repos_includes_private_repos_when_the_token_has_repo_scope():
    """/user/repos (authenticated) sees whatever the token's own scope allows —
    unlike /users/{login}/repos, which is a public-profile listing and can
    never return a private repo for any token."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user/repos"
        return httpx.Response(
            200,
            json=[
                {"owner": {"login": "octodev"}, "name": "public-app", "fork": False, "private": False},
                {"owner": {"login": "octodev"}, "name": "internal-app", "fork": False, "private": True},
            ],
        )

    client = _client(handler)

    repos = client.list_owned_repos("token", "octodev")

    assert {(r.name, r.private) for r in repos} == {("public-app", False), ("internal-app", True)}


def test_list_owned_repos_falls_back_to_public_only_without_repo_scope():
    """A Candidate who connected before private-repo support existed carries a
    token issued under the old, narrower scope. Real production concern: that
    token must keep working exactly as it did before, not break /verify."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            return httpx.Response(403, json={"message": "Resource not accessible by integration"})
        assert request.url.path == "/users/octodev/repos"
        return httpx.Response(
            200, json=[{"owner": {"login": "octodev"}, "name": "public-app", "fork": False}]
        )

    client = _client(handler)

    repos = client.list_owned_repos("token-with-old-scope", "octodev")

    assert [(r.name, r.private) for r in repos] == [("public-app", False)]


def test_list_owned_repos_does_not_fall_back_on_a_mid_pagination_error():
    """The public-only fallback exists for a token that lacks the repo OAuth
    scope, which fails immediately on page 1 of /user/repos. A transient error
    on page 2+ — after page 1 already proved this token DOES have scope
    access — must propagate instead of being silently downgraded to a
    public-only, private-repo-free result for the whole /verify run."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            if request.url.params.get("page") == "2":
                return httpx.Response(502, text="Bad Gateway")
            return httpx.Response(
                200,
                json=[{"owner": {"login": "octodev"}, "name": "repo-a", "fork": False, "private": True}],
                headers={
                    "Link": '<https://api.github.com/user/repos?affiliation=owner&per_page=100&page=2>; rel="next"'
                },
            )
        if request.url.path == "/users/octodev/repos":
            # Only reached if the (buggy) fallback fires; a real fallback
            # response here would mask the bug behind a passing test.
            return httpx.Response(200, json=[{"owner": {"login": "octodev"}, "name": "repo-a", "fork": False}])
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    with pytest.raises(httpx.HTTPStatusError):
        client.list_owned_repos("token", "octodev")


def test_list_merged_prs_follows_pagination_on_the_search_endpoint():
    """The search API wraps results in {"items": [...]} rather than a bare
    array, but still paginates via the same Link header — must aggregate too."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200, json={"items": [{"repository_url": "https://api.github.com/repos/someorg/proj-b", "number": 9}]}
            )
        return httpx.Response(
            200,
            json={"items": [{"repository_url": "https://api.github.com/repos/someorg/proj-a", "number": 5}]},
            headers={"Link": '<https://api.github.com/search/issues?q=x&per_page=100&page=2>; rel="next"'},
        )

    client = _client(handler)

    prs = client.list_merged_prs("token", "octodev")

    assert {(pr.repo.name, pr.number) for pr in prs} == {("proj-a", 5), ("proj-b", 9)}


def test_list_pr_review_comments_follows_link_header_pagination():
    """PR review comments are the exact >100-comments case candidate 2's problem
    statement named — must not be truncated at page 1 either."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 2,
                        "body": "second page comment",
                        "created_at": "2024-01-02T00:00:00Z",
                        "html_url": "https://github.com/octodev/skillproof-lib/pull/1#comment-2",
                        "user": {"login": "octodev"},
                    }
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "body": "first page comment",
                    "created_at": "2024-01-01T00:00:00Z",
                    "html_url": "https://github.com/octodev/skillproof-lib/pull/1#comment-1",
                    "user": {"login": "octodev"},
                }
            ],
            headers={
                "Link": (
                    '<https://api.github.com/repos/octodev/skillproof-lib/pulls/comments'
                    '?per_page=100&page=2>; rel="next"'
                )
            },
        )

    client = _client(handler)

    comments = client.list_pr_review_comments("token", Repo(owner="octodev", name="skillproof-lib"), "octodev")

    assert {c.comment_id for c in comments} == {1, 2}


def test_get_all_pages_logs_a_warning_when_max_pages_is_exhausted(caplog):
    """Any paginated caller relying on the max_pages safety cap must not
    silently truncate results with zero signal — list_pr_review_comments (bug
    3c: oldest-first across the whole repo, so a candidate's own recent
    comments are what gets dropped) and _fetch_owned_commits (bug 3d:
    newest-first, so the dropped tail is the oldest/Span-relevant commits)
    both hit this same cap. One shared check in _get_all_pages covers both."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page") or "1")
        return httpx.Response(
            200,
            json=[{"id": page}],
            headers={
                "Link": (
                    "<https://api.github.com/repos/octodev/big-repo/pulls/comments"
                    f'?per_page=100&page={page + 1}>; rel="next"'
                )
            },
        )

    client = _client(handler)

    with caplog.at_level(logging.WARNING):
        results = client._get_all_pages(
            "token", "/repos/octodev/big-repo/pulls/comments", params={"per_page": 100}, max_pages=3
        )

    assert len(results) == 3  # capped, not the endless pages the fake Link header offers
    assert any("max_pages" in record.message for record in caplog.records)


def test_list_pr_review_comments_skips_deleted_account_comments_without_crashing():
    """GitHub returns "user": null (not a missing key) for a comment whose author's
    account has since been deleted — a real, occasionally-hit case, not a fixture
    artifact. The old `c.get("user", {})` default only covers a missing key; an
    explicit `null` still returns `None`, and calling `.get("login", "")` on that
    raised AttributeError, which killed this repo's whole comment fetch (running in
    ingestion.py's thread pool) and failed every claimed skill's card for the run."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "body": "from a deleted account",
                    "created_at": "2024-01-01T00:00:00Z",
                    "html_url": "https://github.com/octodev/skillproof-lib/pull/1#comment-1",
                    "user": None,
                },
                {
                    "id": 2,
                    "body": "from the candidate",
                    "created_at": "2024-01-02T00:00:00Z",
                    "html_url": "https://github.com/octodev/skillproof-lib/pull/1#comment-2",
                    "user": {"login": "octodev"},
                },
            ],
        )

    client = _client(handler)

    comments = client.list_pr_review_comments("token", Repo(owner="octodev", name="skillproof-lib"), "octodev")

    assert {c.comment_id for c in comments} == {2}


def test_get_authenticated_user_raises_on_revoked_token():
    client = _client(lambda request: httpx.Response(401, json={"message": "Bad credentials"}))

    with pytest.raises(GitHubAuthError):
        client.get_authenticated_user("revoked-token")


def test_follows_a_redirect_instead_of_misreading_the_redirect_body_as_data():
    """A repo renamed/transferred to a new owner answers the old owner/name
    path with a 301, not the resource. Without follow_redirects, GitHub's tiny
    redirect payload ({"message": "Moved Permanently", ...}) was returned as
    if it were the real resource — a confusing KeyError deep in a caller
    instead of a clean, catchable error."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/oldowner/oldname/commits/abc123":
            return httpx.Response(
                301,
                headers={"Location": "https://api.github.com/repos/newowner/newname/commits/abc123"},
                json={"message": "Moved Permanently", "url": "https://api.github.com/repos/newowner/newname/commits/abc123"},
            )
        if request.url.path == "/repos/newowner/newname/commits/abc123":
            return httpx.Response(200, json={"sha": "abc123", "commit": {"message": "real commit"}})
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    body = client._get_json("token", "/repos/oldowner/oldname/commits/abc123")

    assert body == {"sha": "abc123", "commit": {"message": "real commit"}}


def test_repeated_call_reuses_cached_body_on_304():
    """A 304 response (matched ETag) must return the previously cached body, not
    fail on a missing body — the etag caching path was completely untested."""
    etag = 'W/"abc123"'
    next_id = iter([1, 2])  # a broken cache would fetch fresh content on the 2nd call

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("If-None-Match") == etag:
            return httpx.Response(304)
        return httpx.Response(200, json={"id": next(next_id), "login": "octodev"}, headers={"ETag": etag})

    client = _client(handler)

    first = client.get_authenticated_user("token")
    second = client.get_authenticated_user("token")

    assert first.id == 1
    assert second.id == 1  # served from the ETag cache, not a fresh id=2 fetch


def test_pagination_continues_past_a_304_on_a_cached_first_page():
    """The ETag cache only stored (etag, body) — never the Link header. On a
    re-verify where the first page comes back 304, _get_all_pages evaluated
    the FRESH 304 response's Link header (typically absent) instead of the
    original 200's, silently stopping pagination after just page 1."""
    etag = 'W/"abc123"'
    page2_hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            page2_hits["n"] += 1
            return httpx.Response(
                200, json=[{"owner": {"login": "octodev"}, "name": "repo-b", "fork": False, "private": False}]
            )
        if request.headers.get("If-None-Match") == etag:
            return httpx.Response(304)
        return httpx.Response(
            200,
            json=[{"owner": {"login": "octodev"}, "name": "repo-a", "fork": False, "private": False}],
            headers={
                "ETag": etag,
                "Link": '<https://api.github.com/user/repos?affiliation=owner&per_page=100&page=2>; rel="next"',
            },
        )

    client = _client(handler)

    first = client.list_owned_repos("token", "octodev")
    second = client.list_owned_repos("token", "octodev")  # first page now served from the ETag cache (304)

    assert {r.name for r in first} == {"repo-a", "repo-b"}
    assert {r.name for r in second} == {"repo-a", "repo-b"}
    assert page2_hits["n"] == 2


def test_list_qualifying_commits_treats_409_empty_repo_as_zero_commits():
    """GitHub returns 409 Conflict from an owned repo's /commits endpoint when
    the repo has no commits yet (empty, no default branch) — that must be
    treated as zero commits for that repo, not abort the whole scan."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            return httpx.Response(
                200, json=[{"owner": {"login": "octodev"}, "name": "empty-repo", "fork": False, "private": False}]
            )
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/repos/octodev/empty-repo/commits":
            return httpx.Response(409, json={"message": "Git Repository is empty."})
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    commits = client.list_qualifying_commits("token", "octodev")

    assert commits == []


def test_a_vanished_owned_repo_does_not_abort_other_owned_repos_commits():
    """Regression test for a real production crash: a repo in list_owned_repos'
    result can be deleted, renamed, or have access revoked by the time the
    commits fetch for it actually runs. That must skip just this repo's
    commits, not raise and abort every other owned repo's already-gathered
    evidence for the whole /verify run."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            return httpx.Response(
                200,
                json=[
                    {"owner": {"login": "octodev"}, "name": "gone-repo", "fork": False, "private": False},
                    {"owner": {"login": "octodev"}, "name": "fine-repo", "fork": False, "private": False},
                ],
            )
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/repos/octodev/gone-repo/commits":
            return httpx.Response(404, json={"message": "Not Found"})
        if request.url.path == "/repos/octodev/fine-repo/commits":
            return httpx.Response(200, json=[{"sha": "c1"}])
        if request.url.path == "/repos/octodev/fine-repo/commits/c1":
            return httpx.Response(
                200,
                json={
                    "commit": {"message": "msg", "author": {"date": "2024-01-01T00:00:00Z"}},
                    "files": [],
                    "html_url": "https://github.com/octodev/fine-repo/commit/c1",
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    commits = client.list_qualifying_commits("token", "octodev")

    assert [c.sha for c in commits] == ["c1"]


def test_a_vanished_external_repo_does_not_abort_other_merged_prs_commits():
    """Same gap as above, but for an external repo reached via list_merged_prs
    (whose search-index result lags reality even more than an owned repo)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            return httpx.Response(200, json=[])
        if request.url.path == "/search/issues":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"repository_url": "https://api.github.com/repos/someorg/gone-repo", "number": 1},
                        {"repository_url": "https://api.github.com/repos/someorg/fine-repo", "number": 2},
                    ]
                },
            )
        if request.url.path == "/repos/someorg/gone-repo/pulls/1/commits":
            return httpx.Response(403, json={"message": "Forbidden"})
        if request.url.path == "/repos/someorg/fine-repo/pulls/2/commits":
            return httpx.Response(200, json=[{"sha": "e1"}])
        if request.url.path == "/repos/someorg/fine-repo/commits/e1":
            return httpx.Response(
                200,
                json={
                    "commit": {"message": "msg", "author": {"date": "2024-01-01T00:00:00Z"}},
                    "files": [],
                    "html_url": "https://github.com/someorg/fine-repo/commit/e1",
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    commits = client.list_qualifying_commits("token", "octodev")

    assert [c.sha for c in commits] == ["e1"]


def test_list_pr_review_comments_returns_empty_for_a_now_inaccessible_repo():
    """Regression test: this call previously had zero exception handling at
    all, so a 404/403 here raised uncaught and (via ingestion.py's thread pool)
    aborted the entire /verify run for every claimed skill."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client = _client(handler)

    comments = client.list_pr_review_comments("token", Repo(owner="someorg", name="gone-repo"), "octodev")

    assert comments == []


def test_get_manifest_files_skips_a_now_forbidden_file_without_raising():
    """A 403 on one manifest filename (repo access revoked mid-scan) must not
    abort checking the other ~19 MANIFEST_FILENAMES for the same repo."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/requirements.txt"):
            return httpx.Response(403, json={"message": "Forbidden"})
        return httpx.Response(404, json={"message": "Not Found"})

    client = _client(handler)

    files = client.get_manifest_files("token", Repo(owner="octodev", name="skillproof-lib"))

    assert files == {}


def test_get_manifest_files_retries_on_secondary_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(github_client.time, "sleep", lambda seconds: None)
    attempts = {"requirements.txt": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/requirements.txt"):
            return httpx.Response(404, json={"message": "Not Found"})
        attempts["requirements.txt"] += 1
        if attempts["requirements.txt"] == 1:
            return httpx.Response(403, text="secondary rate limit exceeded")
        content = base64.b64encode(b"flask==3.0\n").decode()
        return httpx.Response(200, json={"content": content, "encoding": "base64"})

    client = _client(handler)

    files = client.get_manifest_files("token", Repo(owner="octodev", name="skillproof-lib"))

    assert files["requirements.txt"] == "flask==3.0\n"
    assert attempts["requirements.txt"] == 2  # first call rate-limited, retried once


def test_retries_on_primary_rate_limit_then_succeeds(monkeypatch):
    """GitHub's PRIMARY rate limit (5000 req/hr) returns 403 with
    X-RateLimit-Remaining: 0 and neither a Retry-After header nor "secondary
    rate limit"/"abuse detection" body text — previously falling straight
    through to raise_for_status with zero retry, despite the backoff/retry
    machinery right above already existing for the secondary-limit case."""
    monkeypatch.setattr(github_client.time, "sleep", lambda seconds: None)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(
                403, headers={"X-RateLimit-Remaining": "0"}, json={"message": "API rate limit exceeded"}
            )
        return httpx.Response(200, json={"id": 1, "login": "octodev"})

    client = _client(handler)

    user = client.get_authenticated_user("token")

    assert user.login == "octodev"
    assert attempts["n"] == 2  # first attempt rate-limited, retried once rather than raising


def test_primary_rate_limit_backoff_is_capped_even_when_reset_is_far_out():
    """Real production incident: X-RateLimit-Reset can be up to an hour out,
    and the old backoff computed that full wait uncapped. That sleep runs
    while holding _rate_limit_gate — a lock shared by every GitHub request
    across the whole process, since RealGitHubClient is a process-wide
    singleton — so one candidate's primary rate limit froze GitHub
    connectivity for every concurrent scan on the server, indefinitely, with
    no error and no user-visible signal (this is what "stuck on Checking
    dependency manifests" looks like from the candidate's side)."""
    far_future_reset = str(int(time.time()) + 3000)  # 50 minutes out

    response = httpx.Response(
        403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": far_future_reset},
        json={"message": "API rate limit exceeded"},
        request=httpx.Request("GET", "https://api.github.com/user"),
    )

    assert github_client._backoff_seconds(response, attempt=0) <= 60.0


def test_a_persistently_rate_limited_manifest_file_is_skipped_within_bounded_time(monkeypatch):
    """End-to-end: even if a resource stays primary-rate-limited across every
    retry, the scan must give up within max_retries * the capped backoff and
    skip just that file (task #1's containment), not hang. Uses a fake sleep
    that raises after being called more times than max_retries could ever
    need, so a regression back to the uncapped/unbounded wait would fail this
    test by calling sleep excessively rather than by actually hanging."""
    sleep_calls = {"n": 0}

    def bounded_fake_sleep(seconds: float) -> None:
        assert seconds <= 60.0
        sleep_calls["n"] += 1
        assert sleep_calls["n"] <= 10  # generous ceiling; max_retries=5 by default

    monkeypatch.setattr(github_client.time, "sleep", bounded_fake_sleep)

    far_future_reset = str(int(time.time()) + 3000)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/requirements.txt"):
            return httpx.Response(
                403,
                headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": far_future_reset},
                json={"message": "API rate limit exceeded"},
            )
        return httpx.Response(404, json={"message": "Not Found"})

    client = _client(handler)

    files = client.get_manifest_files("token", Repo(owner="octodev", name="skillproof-lib"))

    assert files == {}  # the persistently-rate-limited file is skipped, not raised
    assert sleep_calls["n"] > 0  # actually exercised the backoff path


def test_get_manifest_files_checks_filenames_concurrently():
    """Manifest detection checks ~20 filenames per repo (github-scan-performance
    ticket 01). Each handler call sleeps briefly, so more than one request in
    flight at once is only possible if they're issued concurrently — a serial
    implementation would never show a peak above 1."""
    tracker = _ConcurrencyTracker()

    def handler(request: httpx.Request) -> httpx.Response:
        tracker.enter()
        try:
            time.sleep(0.05)
            return httpx.Response(404, json={"message": "Not Found"})
        finally:
            tracker.exit()

    client = _client(handler)

    files = client.get_manifest_files("token", Repo(owner="octodev", name="skillproof-lib"))

    assert files == {}
    assert tracker.peak > 1


def test_commit_detail_fetch_runs_concurrently():
    """Fetching each qualifying commit's diff is the N+1 hot path ticket 01
    targets. Assert multiple commit-detail requests are genuinely in flight at
    once, not fetched one at a time."""
    tracker = _ConcurrencyTracker()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            return httpx.Response(
                200, json=[{"owner": {"login": "octodev"}, "name": "repo-a", "fork": False, "private": False}]
            )
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/repos/octodev/repo-a/commits":
            return httpx.Response(200, json=[{"sha": f"sha{i}"} for i in range(5)])
        tracker.enter()
        try:
            time.sleep(0.05)
            return httpx.Response(
                200,
                json={
                    "commit": {"message": "msg", "author": {"date": "2024-01-01T00:00:00Z"}},
                    "files": [],
                    "html_url": "https://github.com/octodev/repo-a/commit/x",
                },
            )
        finally:
            tracker.exit()

    client = _client(handler)

    commits = client.list_qualifying_commits("token", "octodev")

    assert len(commits) == 5
    assert tracker.peak > 1


def test_commit_record_logs_a_warning_when_files_array_hits_the_300_cap(caplog):
    """/repos/{owner}/{repo}/commits/{sha} paginates its "files" array past 300
    entries via Link headers that _get_json never follows — a commit touching
    300+ files silently has its files/diff_text built from only the first
    300. Exactly 300 is the strong signal of truncation (GitHub always caps
    at exactly 300 per page for this field)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            return httpx.Response(
                200, json=[{"owner": {"login": "octodev"}, "name": "repo-a", "fork": False, "private": False}]
            )
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/repos/octodev/repo-a/commits":
            return httpx.Response(200, json=[{"sha": "bigsha"}])
        if request.url.path == "/repos/octodev/repo-a/commits/bigsha":
            return httpx.Response(
                200,
                json={
                    "commit": {"message": "msg", "author": {"date": "2024-01-01T00:00:00Z"}},
                    "files": [{"filename": f"f{i}.py"} for i in range(300)],
                    "html_url": "https://github.com/octodev/repo-a/commit/bigsha",
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    with caplog.at_level(logging.WARNING):
        commits = client.list_qualifying_commits("token", "octodev")

    assert len(commits[0].files) == 300
    assert any("300" in record.message for record in caplog.records)


def test_repos_are_processed_concurrently():
    """Owned repos (github-scan-performance ticket 03) should overlap rather
    than one repo's commit-list call finishing entirely before the next
    starts."""
    tracker = _ConcurrencyTracker()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/repos":
            return httpx.Response(
                200,
                json=[
                    {"owner": {"login": "octodev"}, "name": "repo-a", "fork": False, "private": False},
                    {"owner": {"login": "octodev"}, "name": "repo-b", "fork": False, "private": False},
                ],
            )
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": []})
        if request.url.path.endswith("/commits"):
            tracker.enter()
            try:
                time.sleep(0.05)
                return httpx.Response(200, json=[])
            finally:
                tracker.exit()
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    client.list_qualifying_commits("token", "octodev")

    assert tracker.peak > 1


def test_rate_limit_gate_is_held_by_the_backing_off_thread(monkeypatch):
    """When a request hits a secondary rate limit, the shared gate
    (`_rate_limit_gate`, ticket 02) must be held for the duration of the
    backoff sleep — that's the state that makes every other thread's next
    request block on the same cooldown instead of independently sleeping and
    re-triggering the same limit. Checking the lock's state at the instant
    `time.sleep` is called proves the mechanism directly, without relying on
    real wall-clock timing between threads."""
    observed = {"gate_locked_during_sleep": None}

    def fake_sleep(seconds: float) -> None:
        observed["gate_locked_during_sleep"] = client._rate_limit_gate.locked()

    monkeypatch.setattr(github_client.time, "sleep", fake_sleep)

    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(403, headers={"Retry-After": "1"}, text="secondary rate limit exceeded")
        return httpx.Response(404, json={"message": "Not Found"})

    client = _client(handler)

    client.get_manifest_files("token", Repo(owner="octodev", name="skillproof-lib"))

    assert observed["gate_locked_during_sleep"] is True


def test_client_survives_reuse_across_two_verification_runs(db_session_factory):
    """Regression test for a real production bug (see git history: "Fix: don't
    close the process-wide GitHubClient singleton after a scan"). `deps.get_github_client`
    caches one `RealGitHubClient` for the whole app process (an `@lru_cache`
    singleton), so `run_verification` must leave it usable for the next request —
    not just the one it was called for. This test proves that directly by running
    verification twice against the same client instance, the exact shape of the
    incident (the first completed run permanently broke every later GitHub call,
    including OAuth token exchange, by closing the shared `httpx.Client`)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos"):
            return httpx.Response(200, json=[])
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": []})
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)

    db = db_session_factory()
    candidate = Candidate(
        github_user_id=1,
        github_login="octodev",
        github_token_encrypted=security.encrypt_token("real-token"),
    )
    db.add(candidate)
    db.commit()
    candidate_id = candidate.candidate_id
    db.close()

    for _ in range(2):
        db = db_session_factory()
        candidate = db.get(Candidate, candidate_id)
        verify_service.start_verification(db, candidate, ["FastAPI"])
        db.close()

        verify_service.run_verification(db_session_factory, candidate_id, ["FastAPI"], client)

        db = db_session_factory()
        card = db.query(EvidenceCard).filter_by(candidate_id=candidate_id, skill="FastAPI").one()
        assert card.status == "complete"
        db.close()
