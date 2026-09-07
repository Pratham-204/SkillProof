from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from skillproof import scoring, security, sightings, taxonomy
from skillproof.github_client import GitHubAuthError, GitHubClient
from skillproof.ingestion import ingest_evidence
from skillproof.models import Candidate, EvidenceCard
from skillproof.progress_bus import ProgressEvent, progress_bus
from skillproof.security import TokenDecryptionError

logger = logging.getLogger(__name__)

# A real scan budgets ~1 minute (ADR-0015), even with rate-limit backoff
# headroom -- a "processing" card older than this was not abandoned by a slow
# scan, it was abandoned by a run whose process died before reaching its own
# finally block (most commonly: a deploy replacing the container mid-scan).
# Nothing else ever revisits a "processing" row, so without this bound a
# single interrupted run permanently locks that candidate out of ever
# verifying again -- confirmed in production (a candidate's account was stuck
# on 409 for hours after a deploy killed their scan mid-loop).
STALE_PROCESSING_THRESHOLD = timedelta(minutes=20)


def _age(moment: datetime) -> timedelta:
    """SQLite (tests, single-writer local dev) silently drops tzinfo on
    read-back even for a `DateTime(timezone=True)` column -- confirmed
    empirically -- while Postgres (production) correctly round-trips it.
    `updated_at` is always written via `models._now()` (UTC), so a naive
    value read back is safe to treat as UTC rather than local time."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - moment


class VerificationInFlightError(Exception):
    """Raised by start_verification when this candidate already has a recent
    (within STALE_PROCESSING_THRESHOLD) status="processing" card at the
    moment a new run is about to reset/create rows. Without this, two
    overlapping /verify calls (a double-click, a client retry, two open tabs)
    each schedule their own run_verification background job writing the same
    rows with no locking -- whichever job commits last silently wins,
    discarding the other's freshly-computed result with no error surfaced
    anywhere. A "processing" card older than the threshold is treated as
    abandoned, not in-flight (see STALE_PROCESSING_THRESHOLD)."""


def start_verification(db: Session, candidate: Candidate, skills: list[str]) -> int:
    """Resets/creates EvidenceCard rows to 'processing' synchronously, before the
    background task runs, so a poll right after POST /verify sees "processing".
    Returns the taxonomy_version it stamped those rows with, so the caller can
    hand that exact value to run_verification instead of it re-reading
    taxonomy.taxonomy_version() independently later (which could by then
    return a newer version, if the self-extending taxonomy batch job bumped it
    in the meantime, and cause every card lookup below to miss).

    A re-verify under the same taxonomy_version as the candidate's existing card for
    that skill overwrites it in place, exactly as before. A re-verify under a newer
    taxonomy_version forks a new card instead of mutating the old one (ADR-0005), so
    the old card stays traceable to the taxonomy it was actually scored under.

    Raises VerificationInFlightError instead of proceeding if this candidate
    already has a run in progress (see that class's docstring).
    """
    # Serializes the check-and-mark-processing sequence below against another
    # truly concurrent call for the *same* candidate (two open tabs, a
    # double-click, a client retry racing itself) -- without this, a plain
    # read-then-write "already in flight?" check is a TOCTOU: both calls'
    # SELECT can run before either commits status="processing", so both pass
    # the check and both schedule their own run_verification job writing the
    # same rows with no locking, exactly what VerificationInFlightError exists
    # to prevent. SELECT ... FOR UPDATE on the candidate's own row makes the
    # second concurrent caller block here until the first call's transaction
    # commits (releasing the lock) or rolls back, so it then sees the
    # already-committed "processing" rows and is correctly rejected below.
    # SQLite (used in tests and single-writer local dev) has no row-level
    # locking and silently ignores FOR UPDATE -- harmless there since SQLite
    # already serializes writers at the connection/file level; this only
    # changes behavior under a real concurrent Postgres deployment, which is
    # exactly the gap this guards.
    db.query(Candidate).filter_by(candidate_id=candidate.candidate_id).with_for_update().one()

    in_flight_card = (
        db.query(EvidenceCard).filter_by(candidate_id=candidate.candidate_id, status="processing").first()
    )
    if in_flight_card is not None and _age(in_flight_card.updated_at) < STALE_PROCESSING_THRESHOLD:
        raise VerificationInFlightError(candidate.candidate_id)

    current_version = taxonomy.taxonomy_version()
    for skill in skills:
        card = (
            db.query(EvidenceCard)
            .filter_by(candidate_id=candidate.candidate_id, skill=skill)
            .order_by(EvidenceCard.taxonomy_version.desc())
            .first()
        )
        if card is None or card.taxonomy_version != current_version:
            # Two concurrent /verify calls for the same candidate+skill (a
            # double-click, a client retry) can both reach here seeing no row
            # yet and both try to INSERT one, racing
            # uq_candidate_skill_taxonomy_version. The same thing happens
            # within a single call if the client sends a duplicate skill in
            # `skills` (SessionLocal runs with autoflush=False, so the second
            # entry's query above doesn't see the first entry's own pending
            # insert). A SAVEPOINT scopes the conflict to just this one insert
            # (the same pattern sightings._record_one already uses) instead of
            # poisoning the whole transaction; the loser then re-reads the row
            # the winner just committed and updates that instead of crashing.
            try:
                with db.begin_nested():
                    card = EvidenceCard(candidate_id=candidate.candidate_id, skill=skill, taxonomy_version=current_version)
                    db.add(card)
            except IntegrityError:
                card = (
                    db.query(EvidenceCard)
                    .filter_by(candidate_id=candidate.candidate_id, skill=skill, taxonomy_version=current_version)
                    .one()
                )
        card.status = "processing"
        card.error = None
    db.commit()
    return current_version


def run_verification(
    session_factory, candidate_id: str, skills: list[str], github_client: GitHubClient, taxonomy_version: int
) -> None:
    """The in-process background job (issue 04): ingest -> filter -> score -> persist.

    Runs after the originating request has already returned 202, so it opens
    its own DB session rather than reusing a request-scoped one.

    `taxonomy_version` is exactly what start_verification stamped the
    "processing" rows with, passed through by the caller rather than
    re-derived here -- this job updates the same rows it was launched for even
    if the taxonomy is bumped again while this job is still running.

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

        current_version = taxonomy_version

        def on_repo_scanned(repo_full_name: str) -> None:
            progress_bus.publish(candidate_id, ProgressEvent(kind="scan", detail=repo_full_name))

        def on_phase(description: str) -> None:
            progress_bus.publish(candidate_id, ProgressEvent(kind="phase", detail=description))

        try:
            token = security.decrypt_token(candidate.github_token_encrypted)
            evidence_bundle = ingest_evidence(
                github_client, token, candidate.github_login, on_repo_scanned=on_repo_scanned, on_phase=on_phase
            )
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
        except Exception:  # pragma: no cover - defensive, unexpected ingestion failure
            logger.exception("Evidence ingestion failed for candidate %s", candidate_id)
            for skill in skills:
                _fail_card(db, candidate_id, skill, current_version, "Verification failed due to an internal error")
            db.commit()
            return

        candidate.needs_reconnect = False
        try:
            sightings.record_sightings(db, candidate_id, evidence_bundle.manifests)
            db.commit()
        except Exception:  # pragma: no cover - defensive, unexpected sightings failure
            logger.exception("Recording sightings failed for candidate %s", candidate_id)
            db.rollback()
            for skill in skills:
                _fail_card(db, candidate_id, skill, current_version, "Verification failed due to an internal error")
            db.commit()
            return

        on_phase("Scoring claimed skills")

        for skill in skills:
            # Isolated per skill (ticket 01): a batched embeddings call failing
            # for one skill — e.g. a future network-bound backend erroring or
            # rate-limiting — must not abort the rest of this run. This also
            # covers the card lookup/write/commit that follows a successful
            # score, not just the scoring call itself — without that, an
            # exception there (a transient DB error, a lock timeout) would
            # escape the loop entirely, leaving every remaining skill's card
            # stuck at "processing" forever (the "done" event still fires from
            # the outer finally, but nothing ever flips those cards' status
            # again).
            try:
                result = scoring.score_skill(evidence_bundle, skill)
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
            except Exception:
                logger.exception("Scoring failed for skill %s, candidate %s", skill, candidate_id)
                db.rollback()
                _fail_card(db, candidate_id, skill, current_version, "Could not score this skill due to an internal error")
                db.commit()
                continue
            progress_bus.publish(candidate_id, ProgressEvent(kind="reveal", detail=skill))
    finally:
        # github_client is NOT closed here: `deps.get_github_client` is
        # `@lru_cache`-decorated (a process-wide singleton reused by every
        # request, not created fresh per call), so closing its HTTP client
        # after one run would permanently break it for every later request
        # sharing the same instance — including OAuth token exchange in
        # /auth/github/callback. This was a real production bug: the first
        # completed verification run closed the singleton's httpx.Client,
        # and every GitHub call after that (including reconnect) failed with
        # "Cannot send a request, as the client has been closed."
        progress_bus.publish(candidate_id, ProgressEvent(kind="done", detail=""))
        db.close()


def _fail_card(db: Session, candidate_id: str, skill: str, taxonomy_version: int, error: str) -> None:
    """`error` must already be a short, generic, user-safe message — never raw
    exception text. GET /evidence-card/{candidate_id} is unauthenticated and
    public by design (ADR-0016/CONTEXT.md), so anything stored here is
    effectively broadcast to anyone who knows or guesses a candidate_id; the
    full exception belongs in the server-side log (logger.exception, already
    called by every caller of this function) instead."""
    card = (
        db.query(EvidenceCard)
        .filter_by(candidate_id=candidate_id, skill=skill, taxonomy_version=taxonomy_version)
        .one()
    )
    card.status = "failed"
    card.error = error
