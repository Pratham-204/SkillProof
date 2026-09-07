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
    task (running in a worker thread) to that candidate's open SSE stream(s).
    Publishing with no active subscriber is a harmless no-op — the verify
    job's own correctness never depends on anyone listening.

    Each `subscribe()` call gets its own independent queue, and `publish`
    fans an event out to every subscriber currently registered for that
    candidate_id. A candidate normally has at most one live SSE stream at a
    time, but a second one (a duplicate tab, or a client's EventSource
    auto-reconnecting before the server has noticed the first connection is
    dead) is a routine occurrence, not an error: it must not silently steal
    delivery from — or, on cleanup, evict — a still-active first subscriber. A
    `publish` call for events that happened before any subscriber connected
    (a fast job finishing before the frontend's stream request arrives) is
    simply missed — the stream endpoint's initial "already finished" check
    (ticket 03) is what keeps that case correct rather than hanging, not
    perfect delivery of every transient event.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, list[queue.Queue[ProgressEvent]]] = {}

    def subscribe(self, candidate_id: str) -> queue.Queue[ProgressEvent]:
        q: queue.Queue[ProgressEvent] = queue.Queue()
        with self._lock:
            self._queues.setdefault(candidate_id, []).append(q)
        return q

    def unsubscribe(self, candidate_id: str, q: queue.Queue[ProgressEvent]) -> None:
        """Removes only this specific queue — never another subscriber's —
        even if a second subscribe() for the same candidate_id has since
        registered its own queue alongside this one."""
        with self._lock:
            subscribers = self._queues.get(candidate_id)
            if subscribers is None:
                return
            try:
                subscribers.remove(q)
            except ValueError:
                pass
            if not subscribers:
                del self._queues[candidate_id]

    def publish(self, candidate_id: str, event: ProgressEvent) -> None:
        with self._lock:
            subscribers = list(self._queues.get(candidate_id, ()))
        for q in subscribers:
            q.put(event)


progress_bus = ProgressBus()
