import queue
import threading

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from skillproof import taxonomy, verify_service
from skillproof.db import get_db
from skillproof.deps import get_current_candidate, get_github_client, get_session_factory
from skillproof.github_client import GitHubClient
from skillproof.limiter import limiter
from skillproof.models import Candidate, EvidenceCard
from skillproof.progress_bus import ProgressEvent, progress_bus
from skillproof.schemas import VerifyAccepted, VerifyRequest

router = APIRouter(tags=["verify"])

# /verify is the single most expensive endpoint in the app (a GitHub API scan
# plus embedding computation, run as a background job) -- unlike GET /search,
# nothing throttled it at all before this.
VERIFY_RATE_LIMIT = "10/minute"

# Each poll blocks its worker thread for at most this long, so a client
# disconnect (or the process shutting down) is noticed within one interval
# instead of `events.get()` blocking that thread forever.
_STREAM_POLL_TIMEOUT = 15.0
# If nothing has been published in this long, this run's publisher is never
# coming back (e.g. the process that would have published it was killed
# mid-scan across a redeploy, per progress_bus's own in-memory-only design) --
# give up rather than holding the connection and its thread pool slot open
# indefinitely.
_STREAM_MAX_IDLE_SECONDS = 20 * 60.0

# The stream endpoint is intentionally unauthenticated (see verify_stream's
# docstring), so unlike every other mutating/expensive route it can't lean on
# a session or an existing per-candidate check to bound request volume -- it
# needs its own IP-keyed limit the same way POST /verify does.
VERIFY_STREAM_RATE_LIMIT = "30/minute"

# progress_bus's own docstring says "a candidate normally has at most one live
# SSE stream at a time" -- this enforces that as a real, small cap instead of
# just documenting it. Each open stream repeatedly borrows a slot from
# anyio's shared default thread pool (the same pool Starlette uses to run
# every other synchronous route in this app, and to dispatch
# BackgroundTasks), so an unbounded number of concurrent connections against
# one candidate_id -- trivial to open, since this route requires no auth --
# can starve every other route regardless of the per-connection poll timeout.
_MAX_STREAM_SUBSCRIBERS_PER_CANDIDATE = 4
_stream_subscriber_counts: dict[str, int] = {}
_stream_subscriber_counts_lock = threading.Lock()


def _try_reserve_stream_slot(candidate_id: str) -> bool:
    """Claims one of this candidate's limited concurrent-stream slots.

    Returns False (reserving nothing) once the cap is already reached, so the
    caller can reject the connection instead of letting it queue behind
    however many others are already open.
    """
    with _stream_subscriber_counts_lock:
        current = _stream_subscriber_counts.get(candidate_id, 0)
        if current >= _MAX_STREAM_SUBSCRIBERS_PER_CANDIDATE:
            return False
        _stream_subscriber_counts[candidate_id] = current + 1
        return True


def _release_stream_slot(candidate_id: str) -> None:
    with _stream_subscriber_counts_lock:
        current = _stream_subscriber_counts.get(candidate_id, 0)
        if current <= 1:
            _stream_subscriber_counts.pop(candidate_id, None)
        else:
            _stream_subscriber_counts[candidate_id] = current - 1


def _count_in_flight(session_factory, candidate_id: str) -> bool:
    """Blocking DB check, run off the event loop via anyio.to_thread.run_sync
    (see verify_stream) rather than inline in the async route."""
    db = session_factory()
    try:
        return db.query(EvidenceCard).filter_by(candidate_id=candidate_id, status="processing").count() > 0
    finally:
        db.close()


@router.post("/verify", response_model=VerifyAccepted, status_code=202)
@limiter.limit(VERIFY_RATE_LIMIT)
def verify(
    request: Request,
    payload: VerifyRequest,
    background_tasks: BackgroundTasks,
    candidate: Candidate = Depends(get_current_candidate),
    db: Session = Depends(get_db),
    github_client: GitHubClient = Depends(get_github_client),
    session_factory=Depends(get_session_factory),
) -> VerifyAccepted:
    """Returns immediately; scoring runs as an in-process background task (issue 04).

    Candidate identity comes from the session (ADR-0006), not the request body —
    a candidate_id sent by the client would be trusting a value that's intentionally
    public, which is exactly the gap the session model closes.
    """
    for skill in payload.skills:
        if not taxonomy.is_known_skill(skill):
            raise HTTPException(status_code=400, detail=f"'{skill}' is not a recognized Skill Tag")

    if payload.searchable is not None:
        candidate.searchable = payload.searchable
        db.commit()

    try:
        current_taxonomy_version = verify_service.start_verification(db, candidate, payload.skills)
    except verify_service.VerificationInFlightError as exc:
        raise HTTPException(
            status_code=409, detail="A verification is already in progress for this candidate"
        ) from exc

    background_tasks.add_task(
        verify_service.run_verification,
        session_factory,
        candidate.candidate_id,
        payload.skills,
        github_client,
        current_taxonomy_version,
    )

    return VerifyAccepted(candidate_id=candidate.candidate_id, skills=payload.skills)


@router.get("/verify/{candidate_id}/stream")
@limiter.limit(VERIFY_STREAM_RATE_LIMIT)
async def verify_stream(
    request: Request, candidate_id: str, session_factory=Depends(get_session_factory)
) -> EventSourceResponse:
    """Real progress for an in-flight `/verify` run (ticket 03): a "scan" event
    per repo, a "reveal" event per skill, terminating in "done" — never
    fabricated/simulated progress. No auth required: everything streamed here
    (repo names, skill names) is already public once evidence-card/{candidate_id}
    is, unlike candidate_id-authenticated writes (ADR-0006). Because it's
    unauthenticated, it carries its own IP rate limit (VERIFY_STREAM_RATE_LIMIT)
    and a small per-candidate cap on concurrently open streams (below) — without
    those, an attacker could hold an unbounded number of connections open
    against any in-flight candidate_id, each one repeatedly borrowing a slot
    from anyio's shared thread pool and starving every other synchronous route
    in the app.

    If nothing is currently `processing` for this candidate — the run already
    finished, or never started — this returns a single "done" event and closes
    immediately rather than waiting on a background job that may never publish
    again, satisfying the "reconnect after finished" requirement. This check
    subscribes to progress_bus *before* looking, and unsubscribes again if
    the check comes back "not in flight" — subscribing first closes a race
    where the run finishes (and publishes its terminal "done") in the gap
    between the check and the subscribe call, which would otherwise be missed
    outright (progress_bus never replays events published before a subscriber
    existed) and only be noticed later via the idle-giveup fallback below.

    Uses its own short-lived session for that one check rather than a
    request-scoped `Depends(get_db)` — a streaming response holds its
    dependencies open for the entire stream, and with SQLite's single shared
    test connection (StaticPool), an open request-scoped session here would
    starve `run_verification`'s background-thread session of a connection
    for as long as this stream stays open: a real deadlock, not just a test
    artifact, since the same single-connection pattern is how any pool with a
    small max size would behave under this endpoint's naturally long lifetime.
    That check also runs off the event loop via `anyio.to_thread.run_sync`
    rather than blocking it inline, consistent with how the rest of this
    endpoint already treats blocking work.
    """
    if not _try_reserve_stream_slot(candidate_id):
        raise HTTPException(
            status_code=429, detail="Too many concurrent verification streams for this candidate"
        )

    events: queue.Queue[ProgressEvent] = progress_bus.subscribe(candidate_id)
    try:
        in_flight = await anyio.to_thread.run_sync(_count_in_flight, session_factory, candidate_id)
    except BaseException:
        progress_bus.unsubscribe(candidate_id, events)
        _release_stream_slot(candidate_id)
        raise

    if not in_flight:
        progress_bus.unsubscribe(candidate_id, events)
        _release_stream_slot(candidate_id)

        async def already_finished():
            yield {"event": "done", "data": ""}

        return EventSourceResponse(already_finished())

    async def event_stream():
        idle_seconds = 0.0
        try:
            while True:
                try:
                    event = await anyio.to_thread.run_sync(events.get, True, _STREAM_POLL_TIMEOUT)
                except queue.Empty:
                    idle_seconds += _STREAM_POLL_TIMEOUT
                    if idle_seconds >= _STREAM_MAX_IDLE_SECONDS:
                        # Nothing has published in a very long time -- treat
                        # this the same as a normal completion rather than
                        # holding the connection (and its thread pool slot)
                        # open forever on a run whose publisher is gone.
                        yield {"event": "done", "data": ""}
                        break
                    yield {"event": "keepalive", "data": ""}
                    continue
                idle_seconds = 0.0
                yield {"event": event.kind, "data": event.detail}
                if event.kind == "done":
                    break
        finally:
            progress_bus.unsubscribe(candidate_id, events)
            _release_stream_slot(candidate_id)

    return EventSourceResponse(event_stream())
