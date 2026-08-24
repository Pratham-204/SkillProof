"""Non-interactive entry point for a scheduler to run the self-extending taxonomy's
batch publish job (round 8, ADR-0008) — e.g. a nightly cron invoking:

    python -m skillproof.taxonomy_growth_cli

Which cron/scheduler runs this, and how often, is deployment configuration, not
application code — see the spec's Out of Scope.
"""

from __future__ import annotations

import logging

from skillproof.db import SessionLocal
from skillproof.deps import get_groq_client, get_registry_client
from skillproof.taxonomy_growth import publish_new_skill_tags

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        published = publish_new_skill_tags(db, get_registry_client(), get_groq_client())
        logger.info("Published %d new Skill Tag(s)", published)
    finally:
        db.close()


if __name__ == "__main__":
    main()
