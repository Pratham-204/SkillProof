from __future__ import annotations

import queue
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressEvent:
    """One real, already-happened step of a `/verify` run (ticket 03): a repo
    finished scanning, a skill's Evidence Card finished scoring, or the run is
    over. Never a fabricated/simulated tick — see `verify_service.run_verification`
    and `github_client.GitHubClient.list_qualifying_commits`, the only two
    places that publish these."""

    kind: str  # "scan" | "reveal" | "done"
    detail: str  # repo full_name for "scan", skill name for "reveal", "" for "done"


class ProgressBus:
    """In-process pub/sub keyed by candidate_id, bridging a `/verify` background
    task (running in a worker thread) to that candidate's open SSE stream, if
    one exists. Publishing with no active subscriber is a harmless no-op — the
    verify job's own correctness never depends on anyone listening.

    One subscriber per candidate_id at a time by design: a Candidate watches
    their own single live scan. A `publish` call for events that happened
    before a subscriber connected (a fast job finishing before the frontend's
    stream request arrives) is simply missed — the stream endpoint's initial
    "already finished" check (ticket 03) is what keeps that case correct
    rather than hanging, not perfect delivery of every transient event.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, queue.Queue[ProgressEvent]] = {}

    def subscribe(self, candidate_id: str) -> queue.Queue[ProgressEvent]:
        q: queue.Queue[ProgressEvent] = queue.Queue()
        with self._lock:
            self._queues[candidate_id] = q
        return q

    def unsubscribe(self, candidate_id: str) -> None:
        with self._lock:
            self._queues.pop(candidate_id, None)

    def publish(self, candidate_id: str, event: ProgressEvent) -> None:
        with self._lock:
            q = self._queues.get(candidate_id)
        if q is not None:
            q.put(event)


progress_bus = ProgressBus()
