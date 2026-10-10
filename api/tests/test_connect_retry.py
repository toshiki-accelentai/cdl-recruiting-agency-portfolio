"""connect_with_retry: a short database blip (DNS, pooler restart) must not lose a call.

No database needed: `connect` and `sleep` are replaced by fakes.
"""
import psycopg
import pytest

from app.db import connect_with_retry


class FlakyConnect:
    """Fails `failures` times with OperationalError, then returns a sentinel connection."""

    def __init__(self, failures, error=None):
        self.failures = failures
        self.calls = 0
        self.error = error or psycopg.OperationalError("failed to resolve host 'db.example'")

    def __call__(self, url, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "connection"


def test_returns_connection_without_waiting_when_first_try_works():
    connect, waits = FlakyConnect(0), []
    assert connect_with_retry("url", connect=connect, sleep=waits.append) == "connection"
    assert connect.calls == 1 and waits == []


def test_retries_after_a_short_failure_and_waits_longer_each_time():
    connect, waits = FlakyConnect(2), []
    assert connect_with_retry("url", connect=connect, sleep=waits.append) == "connection"
    assert connect.calls == 3
    assert waits == [0.5, 1.0]


def test_gives_up_after_three_tries_with_the_original_error():
    connect, waits = FlakyConnect(99), []
    with pytest.raises(psycopg.OperationalError, match="failed to resolve"):
        connect_with_retry("url", connect=connect, sleep=waits.append)
    assert connect.calls == 3
    assert waits == [0.5, 1.0]  # no pointless wait after the last try


def test_does_not_retry_errors_that_will_never_succeed():
    connect = FlakyConnect(99, error=psycopg.ProgrammingError("bad connection string"))
    with pytest.raises(psycopg.ProgrammingError):
        connect_with_retry("url", connect=connect, sleep=lambda s: None)
    assert connect.calls == 1
