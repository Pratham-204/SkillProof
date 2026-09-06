"""Round 8 (ADR-0008): recording raw material for the self-extending taxonomy."""

from skillproof.models import Candidate, Sighting
from skillproof.sightings import record_sightings


def _make_candidate(db) -> str:
    candidate = Candidate(github_user_id=1, github_login="octodev", github_token_encrypted="unused-in-this-test")
    db.add(candidate)
    db.commit()
    return candidate.candidate_id


def test_record_sightings_dedupes_the_same_package_across_two_manifest_files(db_session_factory):
    """Regression test for a real production crash: psycopg.errors.UniqueViolation
    on uq_sighting_candidate_repo, with detail
    (ecosystem, package_name, candidate_id, repo)=(pip, cachetools, ..., ...).

    A repo can declare the same unrecognized package in more than one manifest
    file (here, requirements.txt and Pipfile both list "cachetools") — two
    Sighting objects for the exact same key, added within one uncommitted
    session. `SessionLocal` is configured with autoflush=False (db.py), so the
    second file's own pre-check in `_record_one` never saw the first file's
    still-pending insert, and both landed in the same flush's INSERT batch,
    which the database correctly rejected — crashing the whole /verify request
    instead of just skipping the duplicate.
    """
    db = db_session_factory()
    try:
        candidate_id = _make_candidate(db)
        manifests = {
            "octodev/skillproof-lib": {
                "requirements.txt": "cachetools==5.3.0\n",
                "Pipfile": '[packages]\ncachetools = "*"\n',
            }
        }

        record_sightings(db, candidate_id, manifests)
        db.commit()

        sightings = db.query(Sighting).filter_by(candidate_id=candidate_id).all()
        assert [(s.ecosystem, s.package_name, s.repo) for s in sightings] == [
            ("pip", "cachetools", "octodev/skillproof-lib")
        ]
    finally:
        db.close()


def test_record_sightings_survives_a_row_already_committed_by_another_session(db_session_factory):
    """The same race, but across two separate sessions/transactions (two
    overlapping /verify runs for the same candidate) rather than within one —
    the in-memory pre-check can only ever see what its own session has
    committed or added, never another session's still-open transaction."""
    db1 = db_session_factory()
    try:
        candidate_id = _make_candidate(db1)
        db1.add(Sighting(ecosystem="pip", package_name="cachetools", candidate_id=candidate_id, repo="octodev/skillproof-lib"))
        db1.commit()
    finally:
        db1.close()

    db2 = db_session_factory()
    try:
        # A second, independent run for the same candidate re-ingests the same
        # repo and tries to record the Sighting the first run already committed.
        record_sightings(db2, candidate_id, {"octodev/skillproof-lib": {"requirements.txt": "cachetools==5.3.0\n"}})
        db2.commit()

        sightings = db2.query(Sighting).filter_by(candidate_id=candidate_id).all()
        assert len(sightings) == 1
    finally:
        db2.close()
