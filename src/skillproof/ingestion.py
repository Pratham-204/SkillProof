from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from skillproof import heuristics, taxonomy
from skillproof.github_client import CommitRecord, GitHubClient, PrCommentRecord, Repo
from skillproof.taxonomy import DetectionPattern


@dataclass(frozen=True)
class EvidenceItem:
    kind: str  # "commit" | "pr_comment"
    repo: str
    ref: str  # sha or comment id, for display/dedup
    url: str
    text: str  # natural language only (commit message, or PR comment body) — Depth's embedding target
    date: datetime
    files: tuple[str, ...] = ()  # changed file paths; empty for pr_comment items
    diff_text: str = ""  # commit diff content, matched against Volume/Presence content markers; empty for pr_comment

    def matches(self, pattern: DetectionPattern) -> bool:
        """A commit matches via its changed files or its own diff content — never
        its message, which is freely candidate-authored prose, not evidence of
        code touched. A PR comment (no diff of its own) can only match via its
        body text. The one place that states what "matching" means per kind."""
        if self.kind == "commit":
            if any(_file_matches(f, pattern) for f in self.files):
                return True
            return _text_matches(self.diff_text, pattern)
        return _text_matches(self.text, pattern)

    @property
    def is_self_authored(self) -> bool:
        """True for a commit message — written solely by the Candidate, so easy
        to embellish on a trivial change. False for a PR review comment, which
        someone else engaged with and is meaningfully harder to game. Scoring's
        Depth discount keys off this."""
        return self.kind == "commit"


def _file_matches(path: str, pattern: DetectionPattern) -> bool:
    if any(path.lower().endswith(ext.lower()) for ext in pattern.file_extensions):
        return True
    return heuristics.matches_any_filename(path, pattern.config_files)


def _text_matches(text: str, pattern: DetectionPattern) -> bool:
    lower = text.lower()
    if any(marker.lower() in lower for marker in pattern.content_markers):
        return True
    return any(pkg.name.lower() in lower for pkg in pattern.manifest_packages)


@dataclass(frozen=True)
class EvidenceBundle:
    """Everything scoring needs for one Candidate, gathered once per `/verify` call
    (not once per claimed skill): the filtered evidence items, plus each repo's
    manifest file contents for the Presence Signal's declared-dependency check."""

    items: list[EvidenceItem]
    manifests: dict[str, dict[str, str]]  # repo full_name -> {filename: content}


def ingest_evidence(
    client: GitHubClient,
    token: str,
    login: str,
    on_repo_scanned: Callable[[str], None] | None = None,
) -> EvidenceBundle:
    """Pull commit diffs + PR review comments for a Candidate and drop low-signal items.

    Volume-qualifying commit scoping (owned-repo vs. external-repo, PR-membership —
    ADR-0004) is owned entirely by `client.list_qualifying_commits`, not decided here.
    The docs/config-only commit filter and short-PR-comment filter run here, before
    anything is embedded, so scoring never sees low-signal evidence. Manifest files
    are fetched once per repo (hybrid-scoring ticket 02), not once per claimed skill.

    `on_repo_scanned`, forwarded to `list_qualifying_commits`, reports real per-repo
    progress during commit-fetching (the dominant cost here) for the verify SSE
    stream (ticket 03) — it doesn't also cover the separate manifest/PR-comment
    loops below.

    The manifest and PR-review-comment loops below fan out across repos
    concurrently (github-scan-performance ticket 03) via a thread pool local to
    this call, rather than finishing one repo before starting the next. This is
    a separate pool from any `client` keeps internally (e.g. `RealGitHubClient`'s
    own per-manifest-filename pool) — nesting into that one instead would risk
    every one of its workers blocking on a queued task none of them is free to run.
    """
    owned_repos = client.list_owned_public_repos(token, login)
    merged_prs = client.list_merged_prs(token, login)
    external_repos = _dedupe_repos(pr.repo for pr in merged_prs)
    all_repos = owned_repos + external_repos
    protected_filenames = taxonomy.all_detection_pattern_config_files()

    items: list[EvidenceItem] = []

    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="ingest-repo") as pool:
        manifest_futures = [(repo, pool.submit(client.get_manifest_files, token, repo)) for repo in all_repos]
        manifests = {repo.full_name: future.result() for repo, future in manifest_futures}

        for commit in client.list_qualifying_commits(token, login, on_repo_scanned=on_repo_scanned):
            _append_commit_evidence(items, commit, protected_filenames)

        comment_futures = [(repo, pool.submit(client.list_pr_review_comments, token, repo, login)) for repo in all_repos]
        for repo, future in comment_futures:
            for comment in future.result():
                if heuristics.is_low_effort_comment(comment.body):
                    continue
                items.append(_evidence_from_comment(repo, comment))

    return EvidenceBundle(items=items, manifests=manifests)


def _dedupe_repos(repos: Iterable[Repo]) -> list[Repo]:
    seen: dict[str, Repo] = {}
    for repo in repos:
        seen.setdefault(repo.full_name, repo)
    return list(seen.values())


def _append_commit_evidence(
    items: list[EvidenceItem],
    commit: CommitRecord,
    protected_filenames: frozenset[str],
) -> None:
    if heuristics.is_docs_or_config_only_commit(commit.files, protected_filenames):
        return
    if not commit.message.strip() and not commit.diff_text.strip():
        return
    items.append(
        EvidenceItem(
            kind="commit",
            repo=commit.repo.full_name,
            ref=commit.sha,
            url=commit.url,
            text=commit.message.strip(),
            date=commit.date,
            files=tuple(commit.files),
            diff_text=commit.diff_text,
        )
    )


def _evidence_from_comment(repo: Repo, comment: PrCommentRecord) -> EvidenceItem:
    return EvidenceItem(
        kind="pr_comment",
        repo=repo.full_name,
        ref=str(comment.comment_id),
        url=comment.url,
        text=comment.body,
        date=comment.date,
    )
