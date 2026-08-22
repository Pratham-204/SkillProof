from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from skillproof import heuristics, taxonomy
from skillproof.github_client import CommitRecord, GitHubClient, PrCommentRecord, Repo


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


@dataclass(frozen=True)
class EvidenceBundle:
    """Everything scoring needs for one Candidate, gathered once per `/verify` call
    (not once per claimed skill): the filtered evidence items, plus each repo's
    manifest file contents for the Presence Signal's declared-dependency check."""

    items: list[EvidenceItem]
    manifests: dict[str, dict[str, str]]  # repo full_name -> {filename: content}


def ingest_evidence(client: GitHubClient, token: str, login: str) -> EvidenceBundle:
    """Pull commit diffs + PR review comments for a Candidate and drop low-signal items.

    Owned, non-fork repos: Volume counts every commit the author-filtered fetch
    returns, as in hybrid-scoring ticket 02. External (non-owned) repos: Volume
    counts only commits belonging to a PR the Candidate actually opened and had
    merged there (hybrid-scoring ticket 03) — fetched per merged PR, never via a
    blanket author-filtered scan of the repo's full history, which a forked repo
    would trivially satisfy with someone else's commits. The docs/config-only
    commit filter and short-PR-comment filter run here, before anything is
    embedded, so scoring never sees low-signal evidence. Manifest files are
    fetched once per repo (hybrid-scoring ticket 02), not once per claimed skill.
    """
    owned_repos = client.list_owned_public_repos(token, login)
    merged_prs = client.list_merged_prs(token, login)
    external_repos = _dedupe_repos(pr.repo for pr in merged_prs)
    all_repos = owned_repos + external_repos
    protected_filenames = taxonomy.all_detection_pattern_config_files()

    manifests = {repo.full_name: client.get_manifest_files(token, repo) for repo in all_repos}

    items: list[EvidenceItem] = []
    seen_commit_keys: set[tuple[str, str]] = set()

    for repo in owned_repos:
        for commit in client.list_commits(token, repo, login):
            _append_commit_evidence(items, seen_commit_keys, repo, commit, protected_filenames)

    for pr in merged_prs:
        for commit in client.list_pr_commits(token, pr.repo, pr.number):
            _append_commit_evidence(items, seen_commit_keys, pr.repo, commit, protected_filenames)

    for repo in all_repos:
        for comment in client.list_pr_review_comments(token, repo, login):
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
    seen_commit_keys: set[tuple[str, str]],
    repo: Repo,
    commit: CommitRecord,
    protected_filenames: frozenset[str],
) -> None:
    key = (repo.full_name, commit.sha)
    if key in seen_commit_keys:
        return  # the same commit can appear in more than one of a Candidate's merged PRs
    seen_commit_keys.add(key)

    if heuristics.is_docs_or_config_only_commit(commit.files, protected_filenames):
        return
    if not commit.message.strip() and not commit.diff_text.strip():
        return
    items.append(
        EvidenceItem(
            kind="commit",
            repo=repo.full_name,
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
