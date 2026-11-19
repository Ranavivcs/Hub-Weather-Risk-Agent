import pytest

from app.rate_limit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_blocks_after_limit_and_recovers_after_window():
    clock = FakeClock()
    limiter = RateLimiter(max_requests=2, window_seconds=60, clock=clock)
    assert limiter.allow("1.2.3.4") and limiter.allow("1.2.3.4")
    assert not limiter.allow("1.2.3.4")
    clock.now = 61
    assert limiter.allow("1.2.3.4")


def test_limits_are_per_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60, clock=FakeClock())
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("a")


def test_rejected_requests_do_not_extend_the_window():
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60, clock=clock)
    limiter.allow("a")
    clock.now = 30
    assert not limiter.allow("a")   # rejected, not recorded
    clock.now = 61
    assert limiter.allow("a")


def test_rejects_bad_config():
    with pytest.raises(ValueError):
        RateLimiter(max_requests=0, window_seconds=60)
