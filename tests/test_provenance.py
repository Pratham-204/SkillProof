"""Provenance Check (round 11, ADR-0012): silently disqualifies a repo's
commits from Volume/Depth/Span when its earliest commit is found to already
exist elsewhere on GitHub, outside repos its owner controls. Presence
(manifest-based) must never be affected — a manifest declaration carries no
authorship claim to dispute.
"""

from datetime import datetime, timezone

from skillproof import provenance
from skillproof.github_client import FakeGitHubClient, Repo
from skillproof.ingestion import EvidenceBundle, EvidenceItem

_NOW = datetime.now(timezone.utc)
_OWNED_REPO = Repo(owner="octodev", name="copied-project", fork=False)


def _bundle_with_one_owned_repo_commit() -> EvidenceBundle:
    item = EvidenceItem(
        kind="commit",
        repo=_OWNED_REPO.full_name,
        ref="c1",
        url="https://example.com/c1",
        text="some commit",
        date=_NOW,
        files=("app.py",),
        diff_text="+print('hi')",
    )
    manifests = {_OWNED_REPO.full_name: {"requirements.txt": "Django==4.2\n"}}
    return EvidenceBundle(items=[item], manifests=manifests, owned_repos=[_OWNED_REPO])


def test_flagged_repo_commits_excluded_but_manifests_kept(fake_github: FakeGitHubClient, db_session_factory):
    fake_github.earliest_commit_shas[_OWNED_REPO.full_name] = "root-sha"
    fake_github.shas_found_elsewhere["root-sha"] = True
    bundle = _bundle_with_one_owned_repo_commit()
    db = db_session_factory()

    result = provenance.exclude_disqualified_evidence(db, fake_github, "token", bundle)

    assert result.items == []
    assert result.manifests == bundle.manifests  # Presence unaffected


def test_clean_repo_keeps_its_evidence(fake_github: FakeGitHubClient, db_session_factory):
    fake_github.earliest_commit_shas[_OWNED_REPO.full_name] = "root-sha"
    fake_github.shas_found_elsewhere["root-sha"] = False
    bundle = _bundle_with_one_owned_repo_commit()
    db = db_session_factory()

    result = provenance.exclude_disqualified_evidence(db, fake_github, "token", bundle)

    assert result.items == bundle.items


def test_empty_repo_earliest_commit_none_is_not_flagged(fake_github: FakeGitHubClient, db_session_factory):
    # No entry in earliest_commit_shas -> get_earliest_commit_sha returns None (empty repo).
    bundle = _bundle_with_one_owned_repo_commit()
    db = db_session_factory()

    result = provenance.exclude_disqualified_evidence(db, fake_github, "token", bundle)

    assert result.items == bundle.items


def test_positive_match_is_cached_permanently_no_second_lookup(
    fake_github: FakeGitHubClient, db_session_factory, monkeypatch
):
    fake_github.earliest_commit_shas[_OWNED_REPO.full_name] = "root-sha"
    fake_github.shas_found_elsewhere["root-sha"] = True
    bundle = _bundle_with_one_owned_repo_commit()
    db = db_session_factory()

    earliest_calls: list[str] = []
    exists_calls: list[str] = []
    original_earliest = fake_github.get_earliest_commit_sha
    original_exists = fake_github.commit_exists_elsewhere

    def counting_earliest(token, repo):
        earliest_calls.append(repo.full_name)
        return original_earliest(token, repo)

    def counting_exists(token, sha, exclude_owner):
        exists_calls.append(sha)
        return original_exists(token, sha, exclude_owner)

    monkeypatch.setattr(fake_github, "get_earliest_commit_sha", counting_earliest)
    monkeypatch.setattr(fake_github, "commit_exists_elsewhere", counting_exists)

    provenance.exclude_disqualified_evidence(db, fake_github, "token", bundle)
    db.commit()
    provenance.exclude_disqualified_evidence(db, fake_github, "token", bundle)

    # Second call is served entirely from the cached, permanent flag — neither
    # GitHubClient method is invoked again, not just the search half.
    assert len(earliest_calls) == 1
    assert len(exists_calls) == 1


def test_clean_repo_is_rechecked_on_every_call_not_cached(
    fake_github: FakeGitHubClient, db_session_factory, monkeypatch
):
    fake_github.earliest_commit_shas[_OWNED_REPO.full_name] = "root-sha"
    fake_github.shas_found_elsewhere["root-sha"] = False
    bundle = _bundle_with_one_owned_repo_commit()
    db = db_session_factory()

    calls: list[str] = []
    original = fake_github.commit_exists_elsewhere

    def counting(token, sha, exclude_owner):
        calls.append(sha)
        return original(token, sha, exclude_owner)

    monkeypatch.setattr(fake_github, "commit_exists_elsewhere", counting)

    provenance.exclude_disqualified_evidence(db, fake_github, "token", bundle)
    db.commit()
    provenance.exclude_disqualified_evidence(db, fake_github, "token", bundle)

    assert len(calls) == 2  # a clean result is never cached
