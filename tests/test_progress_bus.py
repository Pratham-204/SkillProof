"""ProgressBus previously kept exactly one queue.Queue per candidate_id: a
second subscribe() call for the same candidate_id silently replaced the first
subscriber's queue outright (discarding it and everything published to it from
then on with no signal), and unsubscribe() popped whatever queue was CURRENTLY
registered rather than only its own -- so the first subscriber's own cleanup
could silently evict a second, still-active subscriber's queue too.
"""

from skillproof.progress_bus import ProgressBus, ProgressEvent


def test_two_concurrent_subscribers_for_the_same_candidate_both_receive_events():
    bus = ProgressBus()
    first = bus.subscribe("cand-1")
    second = bus.subscribe("cand-1")

    bus.publish("cand-1", ProgressEvent(kind="scan", detail="repo"))

    assert first.get_nowait() == ProgressEvent(kind="scan", detail="repo")
    assert second.get_nowait() == ProgressEvent(kind="scan", detail="repo")


def test_unsubscribing_one_subscriber_does_not_evict_a_still_active_second_one():
    bus = ProgressBus()
    first = bus.subscribe("cand-1")
    second = bus.subscribe("cand-1")

    bus.unsubscribe("cand-1", first)
    bus.publish("cand-1", ProgressEvent(kind="done", detail=""))

    assert second.get_nowait() == ProgressEvent(kind="done", detail="")
