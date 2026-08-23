"""Ticket 03: real per-repo scan events and per-skill reveal events, never
fabricated progress.

Note on test strategy: Starlette's synchronous `TestClient` (the `client`
fixture used elsewhere) fully drains a streaming response's body before
`.stream()`/`.get()` returns control to the caller — it can't interleave with
a background job running concurrently in another thread the way a real
browser's `EventSource` would (confirmed against both the sync TestClient and
an async `httpx.AsyncClient` + `ASGITransport` variant; both block until the
whole SSE body is available in this harness). So:

- The event *ordering* itself (the real value at risk in this ticket) is
  tested directly against `verify_service.run_verification` and
  `progress_bus`, with no HTTP or concurrency involved — `queue.Queue.put`
  never blocks, so publishing during a synchronous call is enough to observe
  order.
- The "reconnect after already finished" fast path is tested over plain HTTP
  with `client`, since it never needs to wait on a live queue — the response
  completes on its own after one event.

Full live-streaming-over-HTTP (a still-in-flight job's events actually
arriving while a client reads them) is exercised manually against a real
uvicorn server once the frontend consumes this endpoint (ticket 05), not here.
"""

from skillproof import verify_service
from skillproof.models import Candidate
from skillproof.progress_bus import progress_bus
from tests.fixtures.github_fixtures import EXTERNAL_REPO, OWNED_REPO, wire_verified_candidate
from tests.test_api_flow import _connect


def test_run_verification_publishes_real_scan_then_reveal_events_in_order(client, fake_github, db_session_factory):
    """Exercises the real production path: ingest_evidence's on_repo_scanned
    callback (threaded through GitHubClient.list_qualifying_commits) and
    verify_service's per-skill publish, with no HTTP or threading involved —
    `progress_bus.publish` just enqueues, so calling run_verification directly
    and draining the queue afterward is enough to prove real ordering.
    """
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    db = db_session_factory()
    candidate = db.get(Candidate, candidate_id)
    verify_service.start_verification(db, candidate, ["FastAPI", "Rust"])
    db.close()

    q = progress_bus.subscribe(candidate_id)
    verify_service.run_verification(db_session_factory, candidate_id, ["FastAPI", "Rust"], fake_github)

    events = []
    while True:
        event = q.get_nowait()
        events.append((event.kind, event.detail))
        if event.kind == "done":
            break
    progress_bus.unsubscribe(candidate_id)

    scan_events = [detail for kind, detail in events if kind == "scan"]
    reveal_events = [detail for kind, detail in events if kind == "reveal"]

    # Both fixture repos are scanned, in the order list_qualifying_commits
    # visits them (owned repos, then external/PR repos).
    assert scan_events == [OWNED_REPO.full_name, EXTERNAL_REPO.full_name]
    # Skills reveal in claim order, each only after its own card is committed.
    assert reveal_events == ["FastAPI", "Rust"]
    assert events[-1] == ("done", "")


def test_verify_stream_reconnect_after_already_finished_closes_immediately(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    verify_response = client.post("/verify", json={"skills": ["FastAPI"]})
    assert verify_response.status_code == 202  # BackgroundTasks already ran synchronously by here

    response = client.get(f"/verify/{candidate_id}/stream")
    assert response.status_code == 200

    events = _parse_sse_body(response.text)
    assert events == [("done", "")]


def _parse_sse_body(text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    kind = None
    data = ""
    for line in text.splitlines():
        if line == "":
            if kind is not None:
                events.append((kind, data))
            kind, data = None, ""
            continue
        if line.startswith("event:"):
            kind = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data = line[len("data:") :].strip()
    return events
