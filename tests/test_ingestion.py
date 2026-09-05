"""ingest_evidence's manifest and PR-review-comment loops fan out across repos
concurrently (github-scan-performance ticket 03) via a thread pool local to the
call, rather than finishing one repo before starting the next.
"""

import threading
import time
from dataclasses import dataclass, field

from skillproof.github_client import GitHubClient, Repo
from skillproof.ingestion import ingest_evidence


class _ConcurrencyTracker:
    """Records the peak number of overlapping calls, so a test can prove work
    across repos actually overlapped rather than running one repo at a time."""

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


@dataclass
class _SlowManifestClient(GitHubClient):
    """A minimal GitHubClient double whose manifest fetch sleeps briefly per
    repo — just enough to prove `ingest_evidence` issues these calls
    concurrently rather than sequentially, without needing a real network
    double."""

    repos: list[Repo]
    tracker: _ConcurrencyTracker
    revoked_tokens: set[str] = field(default_factory=set)

    def exchange_code_for_token(self, code):  # pragma: no cover - unused by ingest_evidence
        raise NotImplementedError

    def get_authenticated_user(self, token):  # pragma: no cover - unused by ingest_evidence
        raise NotImplementedError

    def list_owned_public_repos(self, token, login):
        return self.repos

    def list_merged_prs(self, token, login):
        return []

    def list_pr_review_comments(self, token, repo, author_login):
        return []

    def get_manifest_files(self, token, repo):
        self.tracker.enter()
        try:
            time.sleep(0.05)
            return {}
        finally:
            self.tracker.exit()

    def _fetch_owned_commits(self, token, repo, author_login):
        return []

    def _fetch_pr_commits(self, token, repo, pr_number):
        return []


def test_ingest_evidence_fetches_manifests_across_repos_concurrently():
    tracker = _ConcurrencyTracker()
    repos = [Repo(owner="octodev", name=f"repo-{i}") for i in range(5)]
    client = _SlowManifestClient(repos=repos, tracker=tracker)

    bundle = ingest_evidence(client, "token", "octodev")

    assert set(bundle.manifests) == {r.full_name for r in repos}
    assert tracker.peak > 1
