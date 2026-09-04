from __future__ import annotations

import logging
from dataclasses import asdict

from sqlalchemy.orm import Session

from skillproof import provenance, scoring, security, sightings, taxonomy
from skillproof.github_client import GitHubAuthError, GitHubClient
from skillproof.ingestion import ingest_evidence
from skillproof.models import Candidate, EvidenceCard
from skillproof.progress_bus import ProgressEvent, progress_bus
from skillproof.security import TokenDecryptionError

logger = logging.getLogger(__name__)


def start_verification(db: Session, candidate: Candidate, skills: list[str]) -> None:
    """Resets/creates EvidenceCard rows to 'processing' synchronously, before the
    background task runs, so a poll right after POST /verify sees "processing".

    A re-verify under the same taxonomy_version as the candidate's existing card for
    that skill overwrites it in place, exactly as before. A re-verify under a newer
    taxonomy_version forks a new card instead of mutating the old one (ADR-0005), so
    the old card stays traceable to the taxonomy it was actually scored under.
    """
    current_version = taxonomy.taxonomy_version()
    for skill in skills:
        card = (
            db.query(EvidenceCard)
            .filter_by(candidate_id=candidate.candidate_id, skill=skill)
            .order_by(EvidenceCard.taxonomy_version.desc())
            .first()
        )
        if card is None or card.taxonomy_version != current_version:
            card = EvidenceCard(candidate_id=candidate.candidate_id, skill=skill, taxonomy_version=current_version)
            db.add(card)
        card.status = "processing"
        card.error = None
    db.commit()


def run_verification(session_factory, candidate_id: str, skills: list[str], github_client: GitHubClient) -> None:
    """The in-process background job (issue 04): ingest -> filter -> score -> persist.

    Runs after the originating request has already returned 202, so it opens
    its own DB session rather than reusing a request-scoped one.

    Publishes real, already-happened progress to `progress_bus` as it goes
    (ticket 03): a "scan" event per repo as ingestion processes it, a "reveal"
    event per skill as its card is individually committed (rather than batched
    in one commit at the end, as before), and a terminal "done" event on every
    exit path via `finally`. Publishing is a no-op if nothing is subscribed.
    """
    db = session_factory()
    try:
        candidate = db.get(Candidate, candidate_id)
        if candidate is None:
            return

        # The exact version start_verification stamped the "processing" rows with,
        # so this job updates the same rows it was launched for even if the
        # taxonomy is bumped again while this job is still running.
        current_version = taxonomy.taxonomy_version()

        def on_repo_scanned(repo_full_name: str) -> None:
            progress_bus.publish(candidate_id, ProgressEvent(kind="scan", detail=repo_full_name))

        try:
            token = security.decrypt_token(candidate.github_token_encrypted)
            evidence_bundle = ingest_evidence(
                github_client, token, candidate.github_login, on_repo_scanned=on_repo_scanned
            )
            # Provenance Check (round 11, ADR-0012): silently excludes any owned
            # repo's evidence whose history was imported rather than genuinely
            # authored, before that evidence ever reaches scoring. Kept inside
            # this same try block since it calls the same GitHubClient and can
            # fail the same ways (revoked token, network error) ingestion can.
            evidence_bundle = provenance.exclude_disqualified_evidence(db, github_client, token, evidence_bundle)
        except GitHubAuthError:
            candidate.needs_reconnect = True
            for skill in skills:
                _fail_card(db, candidate_id, skill, current_version, "GitHub token was revoked; reconnect required")
            db.commit()
            return
        except TokenDecryptionError:
            # Same remedy as a revoked token (reconnect re-issues and re-encrypts
            # it) even though the cause is different — e.g. SKILLPROOF_TOKEN_ENCRYPTION_KEY
            # changed since this token was stored (ticket 09's "must be a persisted key"
            # requirement exists specifically to keep this from happening in production).
            candidate.needs_reconnect = True
            for skill in skills:
                _fail_card(db, candidate_id, skill, current_version, "GitHub token could not be decrypted; reconnect required")
            db.commit()
            return
        except Exception as exc:  # pragma: no cover - defensive, unexpected ingestion failure
            logger.exception("Evidence ingestion failed for candidate %s", candidate_id)
            for skill in skills:
                _fail_card(db, candidate_id, skill, current_version, f"Verification failed: {exc}")
            db.commit()
            return

        candidate.needs_reconnect = False
        sightings.record_sightings(db, candidate_id, evidence_bundle.manifests)
        db.commit()

        for skill in skills:
            # Isolated per skill (ticket 01): a batched embeddings call failing
            # for one skill — e.g. a future network-bound backend erroring or
            # rate-limiting — must not abort the rest of this run. Without this,
            # the exception would propagate out of the loop entirely, leaving
            # every remaining skill's card stuck at "processing" forever (the
            # "done" event still fires from the outer finally, but nothing ever
            # flips those cards' status again).
            try:
                result = scoring.score_skill(evidence_bundle, skill)
            except Exception as exc:
                logger.exception("Scoring failed for skill %s, candidate %s", skill, candidate_id)
                _fail_card(db, candidate_id, skill, current_version, f"Could not score this skill: {exc}")
                db.commit()
                continue
            card = (
                db.query(EvidenceCard)
                .filter_by(candidate_id=candidate_id, skill=skill, taxonomy_version=current_version)
                .one()
            )
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
            # Committed per skill (not batched after the loop) so the reveal
            # event below reflects a card that's actually readable via GET
            # /evidence-card the moment a client receives it.
            db.commit()
            progress_bus.publish(candidate_id, ProgressEvent(kind="reveal", detail=skill))
    finally:
        progress_bus.publish(candidate_id, ProgressEvent(kind="done", detail=""))
        db.close()


def _fail_card(db: Session, candidate_id: str, skill: str, taxonomy_version: int, error: str) -> None:
    card = (
        db.query(EvidenceCard)
        .filter_by(candidate_id=candidate_id, skill=skill, taxonomy_version=taxonomy_version)
        .one()
    )
    card.status = "failed"
    card.error = error
