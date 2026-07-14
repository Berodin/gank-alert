import pytest

from gank_ingester import r2z2 as r2z2_module
from gank_ingester.r2z2 import STUCK_GAP_THRESHOLD, STUCK_TIMEOUT_SECONDS, R2Z2Client


class FakeClock:
    """time.sleep() advances the same clock time.monotonic() reads, so a
    test can simulate minutes passing without any real wall-clock delay."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(r2z2_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(r2z2_module.time, "sleep", clock.sleep)
    return clock


def test_iter_from_yields_immediately_available_packages(monkeypatch, fake_clock):
    client = R2Z2Client.__new__(R2Z2Client)  # skip __init__, no real httpx.Client needed
    monkeypatch.setattr(client, "fetch", lambda seq: {"sequence_id": seq})

    gen = client.iter_from(100)
    first = next(gen)
    second = next(gen)

    assert first == {"sequence_id": 100}
    assert second == {"sequence_id": 101}


def test_iter_from_retries_on_404_then_yields(monkeypatch, fake_clock):
    client = R2Z2Client.__new__(R2Z2Client)
    calls = []

    def fake_fetch(seq):
        calls.append(seq)
        return None if len(calls) < 3 else {"sequence_id": seq}

    monkeypatch.setattr(client, "fetch", fake_fetch)

    gen = client.iter_from(50)
    result = next(gen)

    assert result == {"sequence_id": 50}
    assert calls == [50, 50, 50]  # same sequence retried, not advanced, until it succeeds


def test_iter_from_jumps_forward_when_stuck_far_behind_latest(monkeypatch, fake_clock):
    """Simulates the ingester resuming from a cursor whose sequence file
    has already been purged by R2Z2 (>24h old) -- a 404 on it looks
    identical to 'not produced yet', so without this detection the
    ingester would retry it forever and never process anything new."""
    client = R2Z2Client.__new__(R2Z2Client)
    stuck_sequence = 1000
    latest = stuck_sequence + STUCK_GAP_THRESHOLD + 1

    fetch_calls = []

    def fake_fetch(seq):
        fetch_calls.append(seq)
        if seq == stuck_sequence:
            return None
        return {"sequence_id": seq}  # succeeds once we've jumped forward

    monkeypatch.setattr(client, "fetch", fake_fetch)
    monkeypatch.setattr(client, "latest_sequence", lambda: latest)

    gen = client.iter_from(stuck_sequence)
    result = next(gen)

    assert result == {"sequence_id": latest}
    # advanced straight to latest, not linearly through the whole gap
    assert fetch_calls[-1] == latest
    assert fake_clock.now >= STUCK_TIMEOUT_SECONDS


def test_iter_from_does_not_jump_forward_on_small_gap(monkeypatch, fake_clock):
    """A long stall with only a small gap to the live edge is just a quiet
    period (kill rate varies a lot by time of day) -- must not be treated
    as an expired sequence."""
    client = R2Z2Client.__new__(R2Z2Client)
    stuck_sequence = 1000
    latest = stuck_sequence + 5  # well under STUCK_GAP_THRESHOLD

    fetch_calls = []

    def fake_fetch(seq):
        fetch_calls.append(seq)
        if len(fetch_calls) < 200:
            return None
        return {"sequence_id": seq}

    monkeypatch.setattr(client, "fetch", fake_fetch)
    monkeypatch.setattr(client, "latest_sequence", lambda: latest)

    gen = client.iter_from(stuck_sequence)
    result = next(gen)

    # never jumped -- kept retrying the original stuck sequence
    assert result == {"sequence_id": stuck_sequence}
    assert set(fetch_calls) == {stuck_sequence}
