"""Deepening (architecture review candidate 2): RealGitHubClient previously had
zero test coverage and no pagination handling despite every list-fetching call
passing per_page=100 — a Candidate with more than 100 commits/PRs/comments in
one repo had Volume (the highest-weighted signal) silently truncated at page 1.

RealGitHubClient now accepts an injectable httpx transport (defaulting to a
real network transport), so these tests drive it directly with
`httpx.MockTransport` — no new test dependency, httpx ships this itself.
"""

import base64

import httpx
import pytest

from skillproof import github_client
from skillproof.github_client import GitHubAuthError, RealGitHubClient, Repo


def _client(handler) -> RealGitHubClient:
    return RealGitHubClient(client_id="id", client_secret="secret", transport=httpx.MockTransport(handler))


def test_list_owned_public_repos_follows_link_header_pagination():
    """A plain-array endpoint (repos) spanning two pages must not be truncated
    at page 1 — this is the exact silent-truncation bug candidate 2 flagged."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"owner": {"login": "octodev"}, "name": "repo-b", "fork": False}])
        return httpx.Response(
            200,
            json=[{"owner": {"login": "octodev"}, "name": "repo-a", "fork": False}],
            headers={
                "Link": '<https://api.github.com/users/octodev/repos?type=owner&per_page=100&page=2>; rel="next"'
            },
        )

    client = _client(handler)

    repos = client.list_owned_public_repos("token", "octodev")

    assert {r.name for r in repos} == {"repo-a", "repo-b"}


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


def test_get_authenticated_user_raises_on_revoked_token():
    client = _client(lambda request: httpx.Response(401, json={"message": "Bad credentials"}))

    with pytest.raises(GitHubAuthError):
        client.get_authenticated_user("revoked-token")


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
