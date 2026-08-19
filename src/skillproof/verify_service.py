from __future__ import annotations

import logging
from dataclasses import asdict

from sqlalchemy.orm import Session

from skillproof import scoring, security
from skillproof.github_client import GitHubAuthError, GitHubClient
from skillproof.ingestion import ingest_evidence
from skillproof.models import Candidate, EvidenceCard

logger = logging.getLogger(__name__)


def start_verification(db: Session, candidate: Candidate, skills: list[str]) -> None:
    """Resets/creates EvidenceCard rows to 'processing' synchronously, before the
    background task runs, so a poll right after POST /verify sees "processing".
    """
    for skill in skills:
        card = db.query(EvidenceCard).filter_by(candidate_id=candidate.candidate_id, skill=skill).one_or_none()
        if card is None:
            card = EvidenceCard(candidate_id=candidate.candidate_id, skill=skill)
            db.add(card)
        card.status = "processing"
        card.error = None
    db.commit()


def run_verification(session_factory, candidate_id: str, skills: list[str], github_client: GitHubClient) -> None:
    """The in-process background job (issue 04): ingest -> filter -> score -> persist.

    Runs after the originating request has already returned 202, so it opens
    its own DB session rather than reusing a request-scoped one.
    """
    db = session_factory()
    try:
        candidate = db.get(Candidate, candidate_id)
        if candidate is None:
            return

        try:
            token = security.decrypt_token(candidate.github_token_encrypted)
            evidence_items = ingest_evidence(github_client, token, candidate.github_login)
        except GitHubAuthError:
            candidate.needs_reconnect = True
            for skill in skills:
                _fail_card(db, candidate_id, skill, "GitHub token was revoked; reconnect required")
            db.commit()
            return
        except Exception as exc:  # pragma: no cover - defensive, unexpected ingestion failure
            logger.exception("Evidence ingestion failed for candidate %s", candidate_id)
            for skill in skills:
                _fail_card(db, candidate_id, skill, f"Verification failed: {exc}")
            db.commit()
            return

        candidate.needs_reconnect = False

        for skill in skills:
            result = scoring.score_skill(evidence_items, skill)
            card = db.query(EvidenceCard).filter_by(candidate_id=candidate_id, skill=skill).one()
            card.status = "complete"
            card.error = None
            card.confidence_score = result.confidence_score
            card.evidence_type = result.evidence_type
            card.source_commits = [asdict(ref) for ref in result.source_commits]
            card.temporal_span_days = result.temporal_span_days
            # Re-verification overwrites the card in place; a cached explanation
            # from the prior run no longer matches the freshly scored evidence.
            card.explanation = None
            card.explanation_is_fallback = False

        db.commit()
    finally:
        db.close()


def _fail_card(db: Session, candidate_id: str, skill: str, error: str) -> None:
    card = db.query(EvidenceCard).filter_by(candidate_id=candidate_id, skill=skill).one()
    card.status = "failed"
    card.error = error
