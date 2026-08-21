from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from skillproof import heuristics, taxonomy
from skillproof.github_client import GitHubClient


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

    Covers both the Candidate's own public, non-fork repos and external repos
    where they have at least one merged PR (issue 03). The docs/config-only
    commit filter and short-PR-comment filter run here, before anything is
    embedded, so scoring never sees low-signal evidence. Manifest files are
    fetched once per repo (issue 02), not once per claimed skill.
    """
    repos = client.list_owned_public_repos(token, login) + client.list_external_repos_with_merged_prs(token, login)
    protected_filenames = taxonomy.all_detection_pattern_config_files()

    items: list[EvidenceItem] = []
    manifests: dict[str, dict[str, str]] = {}
    for repo in repos:
        manifests[repo.full_name] = client.get_manifest_files(token, repo)

        for commit in client.list_commits(token, repo, login):
            if heuristics.is_docs_or_config_only_commit(commit.files, protected_filenames):
                continue
            if not commit.message.strip() and not commit.diff_text.strip():
                continue
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

        for comment in client.list_pr_review_comments(token, repo, login):
            if heuristics.is_low_effort_comment(comment.body):
                continue
            items.append(
                EvidenceItem(
                    kind="pr_comment",
                    repo=repo.full_name,
                    ref=str(comment.comment_id),
                    url=comment.url,
                    text=comment.body,
                    date=comment.date,
                )
            )

    return EvidenceBundle(items=items, manifests=manifests)
