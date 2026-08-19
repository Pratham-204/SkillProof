from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from skillproof import heuristics
from skillproof.github_client import GitHubClient


@dataclass(frozen=True)
class EvidenceItem:
    kind: str  # "commit" | "pr_comment"
    repo: str
    ref: str  # sha or comment id, for display/dedup
    url: str
    text: str
    date: datetime


def ingest_evidence(client: GitHubClient, token: str, login: str) -> list[EvidenceItem]:
    """Pull commit diffs + PR review comments for a Candidate and drop low-signal items.

    Covers both the Candidate's own public, non-fork repos and external repos
    where they have at least one merged PR (issue 03). The docs/config-only
    commit filter and short-PR-comment filter run here, before anything is
    embedded, so scoring never sees low-signal evidence.
    """
    repos = client.list_owned_public_repos(token, login) + client.list_external_repos_with_merged_prs(token, login)

    items: list[EvidenceItem] = []
    for repo in repos:
        for commit in client.list_commits(token, repo, login):
            if heuristics.is_docs_or_config_only_commit(commit.files):
                continue
            text = f"{commit.message}\n{commit.diff_text}".strip()
            if not text:
                continue
            items.append(
                EvidenceItem(kind="commit", repo=repo.full_name, ref=commit.sha, url=commit.url, text=text, date=commit.date)
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

    return items
