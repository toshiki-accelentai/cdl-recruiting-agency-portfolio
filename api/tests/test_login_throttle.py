"""C3 step 1(d): too many wrong passwords slow an attacker down without locking the owner out. Written before the code.

Limits are per (client address, username) and per client address, so a stranger can only block their own address.
"""
import pytest
from fastapi.testclient import TestClient

from app.throttle import LoginThrottle
from tests.test_auth import PASSWORD, make_user


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def throttle(clock):
    return LoginThrottle(clock=clock, max_per_user_ip=5, max_per_ip=20, window_seconds=900)


def fail(throttle, times, ip="1.1.1.1", username="demo"):
    for _ in range(times):
        throttle.record_failure(ip, username)


# --- the rule itself, no web ----------------------------------------------------------------------

def test_a_fresh_address_is_allowed(throttle):
    assert throttle.blocked_for("1.1.1.1", "demo") == 0


def test_four_failures_are_allowed_and_the_fifth_blocks(throttle):
    fail(throttle, 4)
    assert throttle.blocked_for("1.1.1.1", "demo") == 0
    fail(throttle, 1)
    assert 0 < throttle.blocked_for("1.1.1.1", "demo") <= 900


def test_the_wait_ends_when_the_oldest_counted_failure_leaves_the_window(throttle, clock):
    for _ in range(5):
        throttle.record_failure("1.1.1.1", "demo")
        clock.now += 10          # failures at t=1000, 1010, 1020, 1030, 1040
    clock.now = 1050
    assert throttle.blocked_for("1.1.1.1", "demo") == 850     # the first failure (1000) expires at 1900
    clock.now = 1901
    assert throttle.blocked_for("1.1.1.1", "demo") == 0


def test_a_good_login_clears_that_users_failures(throttle):
    fail(throttle, 4)
    throttle.record_success("1.1.1.1", "demo")
    fail(throttle, 4)
    assert throttle.blocked_for("1.1.1.1", "demo") == 0


def test_username_case_and_spaces_do_not_dodge_the_limit(throttle):
    for name in ("demo", "Demo", " DEMO ", "demo", "dEmO"):
        throttle.record_failure("1.1.1.1", name)
    assert throttle.blocked_for("1.1.1.1", "demo") > 0


def test_one_address_cannot_lock_out_another(throttle):
    fail(throttle, 5, ip="6.6.6.6")
    assert throttle.blocked_for("6.6.6.6", "demo") > 0
    assert throttle.blocked_for("9.9.9.9", "demo") == 0


def test_one_address_trying_many_usernames_is_blocked_as_a_whole(throttle):
    for i in range(20):
        throttle.record_failure("6.6.6.6", f"user{i}")
    assert throttle.blocked_for("6.6.6.6", "brand-new-name") > 0
    assert throttle.blocked_for("9.9.9.9", "brand-new-name") == 0


def test_memory_stays_bounded_when_many_addresses_fail_once(throttle, clock):
    for i in range(6000):
        throttle.record_failure(f"10.{i // 250}.{i % 250}.1", "demo")
    clock.now += 1000
    throttle.record_failure("1.1.1.1", "demo")
    assert throttle.tracked_keys() <= 4


def test_reset_forgets_everything(throttle):
    fail(throttle, 5)
    throttle.reset()
    assert throttle.blocked_for("1.1.1.1", "demo") == 0


# --- through POST /login --------------------------------------------------------------------------

@pytest.fixture
def web(clean_tables):
    from app.main import app
    return TestClient(app)


def attempt(web, password, username="demo", ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return web.post("/login", data={"username": username, "password": password}, headers=headers)


def test_five_wrong_passwords_then_even_the_right_one_waits(web):
    make_user()
    assert [attempt(web, "wrong").status_code for _ in range(5)] == [401] * 5
    r = attempt(web, PASSWORD)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert "set-cookie" not in r.headers


def test_the_right_password_after_four_wrong_ones_works_and_resets_the_count(web):
    make_user()
    for _ in range(4):
        attempt(web, "wrong")
    assert attempt(web, PASSWORD).status_code == 200
    assert [attempt(web, "wrong").status_code for _ in range(4)] == [401] * 4  # a fresh count, not 429


def test_the_limit_follows_the_real_client_address_behind_the_proxy(web):
    make_user()
    for _ in range(5):
        attempt(web, "wrong", ip="203.0.113.5")
    assert attempt(web, PASSWORD, ip="203.0.113.5").status_code == 429
    assert attempt(web, PASSWORD, ip="198.51.100.7").status_code == 200


def test_unknown_usernames_count_too_and_the_answer_does_not_reveal_who_exists(web):
    make_user()
    for i in range(20):
        attempt(web, "x", username=f"ghost{i}", ip="203.0.113.5")
    stranger = attempt(web, "x", username="ghost-new", ip="203.0.113.5")
    known = attempt(web, "x", username="demo", ip="203.0.113.5")
    assert stranger.status_code == known.status_code == 429
    assert stranger.json() == known.json()
