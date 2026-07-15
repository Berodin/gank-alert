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


def test_not_due_before_delay_elapses(fake_clock: FakeClock):
    queue = RecheckQueue(delay_seconds=180)
    queue.add(_event(1))

    fake_clock.now = 179
    assert queue.pop_due() == []
    assert len(queue) == 1


def test_due_once_delay_elapses(fake_clock: FakeClock):
    queue = RecheckQueue(delay_seconds=180)
    event = _event(1)
    queue.add(event)

    fake_clock.now = 180
    due = queue.pop_due()

    assert due == [event]
    assert len(queue) == 0  # popped, single-shot


def test_pop_due_only_returns_each_item_once(fake_clock: FakeClock):
    queue = RecheckQueue(delay_seconds=180)
    queue.add(_event(1))

    fake_clock.now = 500
    first = queue.pop_due()
    second = queue.pop_due()

    assert len(first) == 1
    assert second == []


def test_multiple_items_due_at_different_times(fake_clock: FakeClock):
    queue = RecheckQueue(delay_seconds=180)
    queue.add(_event(1))
    fake_clock.now = 100
    queue.add(_event(2))

    fake_clock.now = 180
    due = queue.pop_due()
    assert [e.killmail_id for e in due] == [1]

    fake_clock.now = 280
    due = queue.pop_due()
    assert [e.killmail_id for e in due] == [2]


def test_adding_same_killmail_id_again_replaces_and_resets_timer(fake_clock: FakeClock):
    queue = RecheckQueue(delay_seconds=180)
    queue.add(_event(1))

    fake_clock.now = 150
    queue.add(_event(1))  # re-added, e.g. seen again -- timer restarts

    fake_clock.now = 180
    assert queue.pop_due() == []  # only 30s since the re-add

    fake_clock.now = 330
    assert len(queue.pop_due()) == 1
