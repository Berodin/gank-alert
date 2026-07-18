import pytest

from gank_ingester import recheck as recheck_module
from gank_ingester.recheck import RecheckQueue
from gank_shared.models import GankEvent, Participant


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(recheck_module.time, "monotonic", clock.monotonic)
    return clock


def _event(killmail_id: int) -> GankEvent:
    return GankEvent(
        killmail_id=killmail_id,
        killmail_hash="x",
        occurred_at="2026-01-01T00:00:00+00:00",
        solar_system_id=1,
        victim=Participant(ship_type_id=1),
        attackers=[],
        sequence_id=1,
        labels=["loc:highsec"],
    )


def test_not_due_before_first_interval_elapses(fake_clock: FakeClock):
    queue = RecheckQueue(intervals=[180, 300])
    queue.add(_event(1))

    fake_clock.now = 179
    assert queue.pop_due() == []
    assert len(queue) == 1


def test_due_at_first_interval_with_attempt_zero(fake_clock: FakeClock):
    queue = RecheckQueue(intervals=[180, 300])
    event = _event(1)
    queue.add(event)

    fake_clock.now = 180
    due = queue.pop_due()

    assert due == [(event, 0)]
    assert len(queue) == 0  # popped


def test_reschedule_queues_next_attempt(fake_clock: FakeClock):
    queue = RecheckQueue(intervals=[180, 300])
    event = _event(1)
    queue.add(event)

    fake_clock.now = 180
    [(popped_event, attempt)] = queue.pop_due()
    assert queue.reschedule(popped_event, attempt) is True
    assert len(queue) == 1

    # not due yet -- only 299s since reschedule, needs 300
    fake_clock.now = 180 + 299
    assert queue.pop_due() == []

    fake_clock.now = 180 + 300
    due = queue.pop_due()
    assert due == [(event, 1)]


def test_reschedule_returns_false_once_retries_exhausted(fake_clock: FakeClock):
    queue = RecheckQueue(intervals=[180, 300])
    event = _event(1)
    queue.add(event)

    fake_clock.now = 180
    [(_, attempt)] = queue.pop_due()
    queue.reschedule(event, attempt)  # -> attempt 1

    fake_clock.now = 180 + 300
    [(_, attempt)] = queue.pop_due()
    assert queue.reschedule(event, attempt) is False  # no more intervals
    assert len(queue) == 0


def test_pop_due_only_returns_each_item_once(fake_clock: FakeClock):
    queue = RecheckQueue(intervals=[180, 300])
    queue.add(_event(1))

    fake_clock.now = 500
    first = queue.pop_due()
    second = queue.pop_due()

    assert len(first) == 1
    assert second == []


def test_adding_same_killmail_id_again_is_a_no_op(fake_clock: FakeClock):
    """Don't reset an item's schedule just because the ingester happens to
    see the same not-yet-ganked kill again before its recheck is due."""
    queue = RecheckQueue(intervals=[180, 300])
    queue.add(_event(1))

    fake_clock.now = 150
    queue.add(_event(1))  # already queued, should be ignored

    fake_clock.now = 180
    assert len(queue.pop_due()) == 1  # still due at the original 180s mark
