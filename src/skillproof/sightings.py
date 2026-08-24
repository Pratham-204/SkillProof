"""Records Sightings during ingestion (round 8, ADR-0008): raw material for the
self-extending taxonomy's batch publish job, not evidence and never scored.
"""

from __future__ import annotations

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
    already_recorded = (
        db.query(Sighting)
        .filter_by(ecosystem=ecosystem, package_name=package_name, candidate_id=candidate_id, repo=repo)
        .first()
        is not None
    )
    if already_recorded:
        return
    db.add(Sighting(ecosystem=ecosystem, package_name=package_name, candidate_id=candidate_id, repo=repo))
