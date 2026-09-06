"""Records Sightings during ingestion (round 8, ADR-0008): raw material for the
self-extending taxonomy's batch publish job, not evidence and never scored.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from skillproof import manifest_parsing, taxonomy
from skillproof.models import Sighting


def record_sightings(db: Session, candidate_id: str, manifests: dict[str, dict[str, str]]) -> None:
    """For every manifest file ingestion already fetched, records a Sighting for each
    declared package matching no existing Skill Tag's Detection Pattern. Idempotent:
    re-verifying the same candidate against the same repo/package never adds a
    duplicate row (`Sighting`'s unique constraint), so repeated `/verify` calls don't
    inflate the distinct-candidate count the batch job later aggregates over. Does
    not commit — the caller (`verify_service.run_verification`) controls the
    transaction boundary.
    """
    known = taxonomy.known_manifest_package_names()
    for repo, files in manifests.items():
        for filename, content in files.items():
            parsed = manifest_parsing.extract_declared_packages(filename, content)
            if parsed is None:
                continue
            ecosystem, package_names = parsed
            for name in package_names:
                if taxonomy.ManifestPackage(ecosystem=ecosystem, name=name.lower()) in known:
                    continue
                _record_one(db, ecosystem=ecosystem, package_name=name, candidate_id=candidate_id, repo=repo)


def _record_one(db: Session, *, ecosystem: str, package_name: str, candidate_id: str, repo: str) -> None:
    """The pre-check below only rules out the common case (this exact candidate
    already has this Sighting, committed, visible to this session). It cannot see
    a second /verify run for the same candidate that is concurrently ingesting the
    same repo in its own, still-open transaction — a real production incident, not
    a hypothetical: two overlapping runs each passed this check, then both tried to
    insert the same row, and the loser crashed the whole request with an unhandled
    UniqueViolation instead of just skipping a Sighting nothing needed it to add.

    The `uq_sighting_candidate_repo` constraint is the actual idempotency
    guarantee; this function's job is just to not treat losing that race as a
    real failure. `begin_nested()` (a SAVEPOINT) scopes the insert so a conflict
    only unwinds this one row, not every Sighting already flushed earlier in the
    same `record_sightings` call or the caller's own transaction — a plain
    `db.add()` here would poison the whole session on conflict instead.
    """
    already_recorded = (
        db.query(Sighting)
        .filter_by(ecosystem=ecosystem, package_name=package_name, candidate_id=candidate_id, repo=repo)
        .first()
        is not None
    )
    if already_recorded:
        return
    try:
        with db.begin_nested():
            db.add(Sighting(ecosystem=ecosystem, package_name=package_name, candidate_id=candidate_id, repo=repo))
    except IntegrityError:
        pass
