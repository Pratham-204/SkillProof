"""Batch job: turns accumulated Sightings into published Skill Tags, with no human
approval step (round 8, ADR-0008) — guarded by a registry-existence check, an
exact-name dedup, and an LLM draft-or-abstain step that also checks semantic
duplication. Not wired into `/verify` or any HTTP route; a scheduler invokes
`publish_new_skill_tags` directly (see `taxonomy_growth_cli.py`), on a fixed cadence
chosen to bound how often the global `taxonomy_version` bump forks every Candidate's
Evidence Cards (ADR-0005).
"""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from skillproof import taxonomy
from skillproof.groq_client import GroqClient, GroqUnavailableError
from skillproof.models import Sighting, SightingDecision
from skillproof.registry_client import RegistryClient

logger = logging.getLogger(__name__)

# An informed prior, not fitted — recalibration is expected once real sighting
# volume exists, the same posture as the Confidence Score's weights (round 6).
MIN_DISTINCT_CANDIDATES = 3


def publish_new_skill_tags(db: Session, registry_client: RegistryClient, groq_client: GroqClient) -> int:
    """Evaluates every eligible (ecosystem, package_name) pair and publishes what
    clears every guard. Returns the number of Skill Tags published this run.

    Commits the `SightingDecision` bookkeeping itself (and the taxonomy file's
    version bump, if anything published) — this is the batch job's own transaction
    boundary, not something a caller manages.
    """
    new_entries: list[taxonomy.SkillTag] = []

    for pair in _eligible_pairs(db):
        if not registry_client.exists(pair.ecosystem, pair.name):
            continue  # not decided — worth retrying once the package might really exist

        if _is_name_duplicate(pair.name):
            _mark_decided(db, pair, "rejected_duplicate")
            continue

        try:
            draft = groq_client.draft_skill_tag(pair.name, pair.ecosystem, taxonomy.list_skills())
        except GroqUnavailableError:
            logger.warning("draft_skill_tag failed for %s/%s; will retry next run", pair.ecosystem, pair.name)
            continue  # not decided — an infrastructure failure, not a judgment

        if draft is not None and draft.category not in taxonomy.CATEGORIES:
            draft = None  # a category outside the fixed five is treated as an abstain

        if draft is None:
            _mark_decided(db, pair, "abstained")
            continue

        new_entries.append(
            taxonomy.SkillTag(
                name=draft.name,
                category=draft.category,
                description=draft.description,
                detection_pattern=taxonomy.DetectionPattern(manifest_packages=(pair,)),
            )
        )
        _mark_decided(db, pair, "published")

    if new_entries:
        taxonomy.append_skill_tags(new_entries)

    db.commit()
    return len(new_entries)


def _eligible_pairs(db: Session) -> list[taxonomy.ManifestPackage]:
    decided = {(d.ecosystem, d.package_name) for d in db.query(SightingDecision).all()}
    rows = (
        db.query(Sighting.ecosystem, Sighting.package_name)
        .group_by(Sighting.ecosystem, Sighting.package_name)
        .having(func.count(func.distinct(Sighting.candidate_id)) >= MIN_DISTINCT_CANDIDATES)
        .all()
    )
    return [
        taxonomy.ManifestPackage(ecosystem=ecosystem, name=package_name)
        for ecosystem, package_name in rows
        if (ecosystem, package_name) not in decided
    ]


def _is_name_duplicate(package_name: str) -> bool:
    existing_names = {s.name.lower() for s in taxonomy.list_skills()}
    return package_name.lower() in existing_names


def _mark_decided(db: Session, pair: taxonomy.ManifestPackage, decision: str) -> None:
    db.add(SightingDecision(ecosystem=pair.ecosystem, package_name=pair.name, decision=decision))
