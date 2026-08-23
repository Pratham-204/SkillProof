import queue

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from skillproof import taxonomy, verify_service
from skillproof.db import get_db
from skillproof.deps import get_current_candidate, get_github_client, get_session_factory
from skillproof.github_client import GitHubClient
from skillproof.models import Candidate, EvidenceCard
from skillproof.progress_bus import ProgressEvent, progress_bus
from skillproof.schemas import VerifyAccepted, VerifyRequest

router = APIRouter(tags=["verify"])


@router.post("/verify", response_model=VerifyAccepted, status_code=202)
def verify(
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

    verify_service.start_verification(db, candidate, payload.skills)

    background_tasks.add_task(
        verify_service.run_verification, session_factory, candidate.candidate_id, payload.skills, github_client
    )

    return VerifyAccepted(candidate_id=candidate.candidate_id, skills=payload.skills)


@router.get("/verify/{candidate_id}/stream")
async def verify_stream(candidate_id: str, session_factory=Depends(get_session_factory)) -> EventSourceResponse:
    """Real progress for an in-flight `/verify` run (ticket 03): a "scan" event
    per repo, a "reveal" event per skill, terminating in "done" — never
    fabricated/simulated progress. No auth required: everything streamed here
    (repo names, skill names) is already public once evidence-card/{candidate_id}
    is, unlike candidate_id-authenticated writes (ADR-0006).

    If nothing is currently `processing` for this candidate — the run already
    finished, or never started — this returns a single "done" event and closes
    immediately rather than waiting on a background job that may never publish
    again, satisfying the "reconnect after finished" requirement.

    Uses its own short-lived session for that one check rather than a
    request-scoped `Depends(get_db)` — a streaming response holds its
    dependencies open for the entire stream, and with SQLite's single shared
    test connection (StaticPool), an open request-scoped session here would
    starve `run_verification`'s background-thread session of a connection
    for as long as this stream stays open: a real deadlock, not just a test
    artifact, since the same single-connection pattern is how any pool with a
    small max size would behave under this endpoint's naturally long lifetime.
    """
    db = session_factory()
    try:
        in_flight = db.query(EvidenceCard).filter_by(candidate_id=candidate_id, status="processing").count() > 0
    finally:
        db.close()

    if not in_flight:

        async def already_finished():
            yield {"event": "done", "data": ""}

        return EventSourceResponse(already_finished())

    events: queue.Queue[ProgressEvent] = progress_bus.subscribe(candidate_id)

    async def event_stream():
        try:
            while True:
                event = await anyio.to_thread.run_sync(events.get)
                yield {"event": event.kind, "data": event.detail}
                if event.kind == "done":
                    break
        finally:
            progress_bus.unsubscribe(candidate_id)

    return EventSourceResponse(event_stream())
