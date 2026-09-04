"""Provenance Check (round 11, ADR-0012): silently disqualifies a repo's
commits from Volume/Depth/Span when its earliest commit is found to already
exist elsewhere on GitHub, outside repos its owner controls — evidence the
repo's history was imported rather than genuinely authored. Closes a gap
ADR-0004's existing anti-gaming corrections leave open: those only scope
external (non-owned) repos via PR-membership, never checking whether an
owned, non-fork repo's commits were actually authored by its owner at all.

Runs as its own step in `verify_service.py`, right after `ingest_evidence`
returns and before scoring — the same shape as `sightings.record_sightings`,
operating on data already gathered rather than being woven into ingestion
itself. Does not commit — the caller controls the transaction boundary.
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy.orm import Session

from skillproof.github_client import GitHubClient, Repo
from skillproof.ingestion import EvidenceBundle
from skillproof.models import RepoProvenanceFlag


def exclude_disqualified_evidence(
    db: Session, client: GitHubClient, token: str, bundle: EvidenceBundle
) -> EvidenceBundle:
    """Every EvidenceItem belonging to a flagged owned repo is removed;
    `manifests` is returned untouched, since a manifest declaration carries no
    authorship claim for the Provenance Check to dispute — Presence never
    reflects a match."""
    flagged_repos = {repo.full_name for repo in bundle.owned_repos if _is_flagged(db, client, token, repo)}
    if not flagged_repos:
        return bundle
    filtered_items = [item for item in bundle.items if item.repo not in flagged_repos]
    return replace(bundle, items=filtered_items)


def _is_flagged(db: Session, client: GitHubClient, token: str, repo: Repo) -> bool:
    """A cached positive match is permanent. An uncached repo is checked fresh
    every time — a clean result today doesn't guarantee one tomorrow, so it's
    deliberately never recorded as cleared."""
    if db.get(RepoProvenanceFlag, repo.full_name) is not None:
        return True

    sha = client.get_earliest_commit_sha(token, repo)
    if sha is None:
        return False
    if not client.commit_exists_elsewhere(token, sha, exclude_owner=repo.owner):
        return False

    db.add(RepoProvenanceFlag(repo=repo.full_name, matched_sha=sha))
    return True
