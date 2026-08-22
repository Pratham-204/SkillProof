"""Deepening: GitHubClient's PR-membership safety property (ADR-0004) moves
from ingestion's caller discipline into the interface itself.
`list_commits`/`list_pr_commits` are gone — `list_qualifying_commits` is the
only way to get a Candidate's Volume-qualifying commits, and it owns the
owned-repo vs. external-repo scoping internally. This is the first direct
test against GitHubClient's own interface (previously only exercised
indirectly through ingestion/scoring in test_api_flow.py).
"""

from datetime import datetime, timezone

from skillproof.github_client import CommitRecord, FakeGitHubClient, MergedPullRequest, Repo
from tests.fixtures.github_fixtures import wire_verified_candidate


def test_list_qualifying_commits_excludes_external_commit_not_in_any_merged_pr(fake_github: FakeGitHubClient):
    """The fixture's external repo has an author-matching commit
    ('e2-not-in-any-merged-pr') that isn't part of the Candidate's merged PR
    there. Proving FakeGitHubClient's own list_qualifying_commits excludes it
    — not just that ingestion never calls the old unsafe method — is what
    makes the anti-gaming defense structural rather than a caller convention.
    """
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    token = fake_github.exchange_code_for_token("test-code")

    commits = fake_github.list_qualifying_commits(token, "octodev")

    shas = {c.sha for c in commits}
    assert shas == {"c1", "c2-docs-only", "e1"}
    assert "e2-not-in-any-merged-pr" not in shas


def test_list_qualifying_commits_dedupes_a_commit_shared_by_two_merged_prs(fake_github: FakeGitHubClient):
    """The same commit sha can appear in more than one of a Candidate's merged
    PRs (e.g. a shared base commit) — it must only count once."""
    repo = Repo(owner="someorg", name="shared-history", fork=False)
    shared_commit = CommitRecord(
        repo=repo,
        sha="shared-sha",
        message="Shared commit",
        date=datetime.now(timezone.utc),
        files=["app.py"],
        diff_text="+print('hi')",
        url="https://github.com/someorg/shared-history/commit/shared-sha",
    )

    fake_github.tokens_by_code["code"] = "token"
    fake_github.owned_repos["octodev"] = []
    fake_github.merged_prs["octodev"] = [
        MergedPullRequest(repo=repo, number=1),
        MergedPullRequest(repo=repo, number=2),
    ]
    fake_github.pr_commits[(repo.full_name, 1)] = [shared_commit]
    fake_github.pr_commits[(repo.full_name, 2)] = [shared_commit]

    commits = fake_github.list_qualifying_commits("token", "octodev")

    assert len(commits) == 1
