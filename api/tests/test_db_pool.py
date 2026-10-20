"""Fix A: the API keeps a few database connections open and reuses them, instead of dialing a new one per
request (about 250 ms each against Supabase). Written before the code.

min 1 and max 4 connections. A connection that died is replaced; work is committed on success and rolled
back on error; a request never waits longer than a few seconds.
"""
import threading
import time
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db
from tests.conftest import TEST_URL
from tests.test_auth import PASSWORD, make_user

APP = Path(__file__).resolve().parents[1] / "app"
REQUEST_PATH_MODULES = ["applicants", "auth", "call_reports", "corrections", "dashboard", "follow_up", "main", "todo"]


@pytest.fixture(autouse=True)
def fresh_pools():
    """Each test starts and ends with no pools, so a test that uses a bad address cannot leak into the next."""
    db.close_pools()
    yield
    db.close_pools()


def backend_pid():
    with db.db_connection(TEST_URL) as conn:
        return conn.execute("SELECT pg_backend_pid()").fetchone()[0]


# --- the pool itself ------------------------------------------------------------------------------

def test_pool_size_is_one_to_four(clean_tables):
    pool = db.get_pool(TEST_URL)
    assert (pool.min_size, pool.max_size) == (1, 4)


def test_the_same_pool_is_reused_for_the_same_address(clean_tables):
    assert db.get_pool(TEST_URL) is db.get_pool(TEST_URL)


def test_sequential_requests_reuse_one_connection_once_the_pool_is_ready(clean_tables):
    db.get_pool(TEST_URL).wait(timeout=10)  # the first connection is open
    pids = {backend_pid() for _ in range(10)}
    assert len(pids) == 1


def test_the_number_of_connections_does_not_grow_with_the_number_of_requests(clean_tables):
    """Even if a request arrives while the first connection is still opening (the pool then adds a second),
    twenty requests in a row still use at most two connections: nothing is dialed per request."""
    pids = {backend_pid() for _ in range(20)}
    assert len(pids) <= 2


def test_at_most_four_connections_and_extra_requests_wait_their_turn(clean_tables):
    pids, errors = [], []

    def work():
        try:
            with db.db_connection(TEST_URL) as conn:
                pid = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
                conn.execute("SELECT pg_sleep(0.3)")
                pids.append(pid)
        except Exception as exc:  # noqa: BLE001 - the test reports any failure
            errors.append(repr(exc))

    started = time.perf_counter()
    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join(timeout=20) for t in threads]
    elapsed = time.perf_counter() - started
    assert errors == [] and len(pids) == 8
    assert len(set(pids)) <= 4
    assert elapsed >= 0.55  # 8 jobs of 0.3 s on at most 4 connections: two rounds, so they did queue


def test_a_connection_the_server_killed_is_replaced_not_handed_out(clean_tables):
    # exactly one connection exists, so the one we kill is the one the next request would be given
    pool = db.get_pool(TEST_URL)
    pool.wait(timeout=10)
    assert pool.get_stats()["pool_size"] == 1
    first = backend_pid()
    with psycopg.connect(TEST_URL, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (first,))
    time.sleep(0.2)
    second = backend_pid()  # must work: the pool notices the dead connection and opens a new one
    assert second != first


def test_work_is_committed_on_success(clean_tables):
    with db.db_connection(TEST_URL) as conn:
        conn.execute("INSERT INTO applicants (name, phone_e164, temperature) VALUES ('Pool Test', '+15550001111', 'COLD')")
    with psycopg.connect(TEST_URL) as other:
        assert other.execute("SELECT count(*) FROM applicants WHERE name = 'Pool Test'").fetchone()[0] == 1


def test_work_is_rolled_back_on_error_and_the_connection_comes_back_clean(clean_tables):
    with pytest.raises(RuntimeError):
        with db.db_connection(TEST_URL) as conn:
            conn.execute("INSERT INTO applicants (name, phone_e164, temperature) VALUES ('Never', '+15550002222', 'COLD')")
            raise RuntimeError("boom")
    with psycopg.connect(TEST_URL) as other:
        assert other.execute("SELECT count(*) FROM applicants WHERE name = 'Never'").fetchone()[0] == 0
    with db.db_connection(TEST_URL) as conn:  # the same connection, handed to the next request
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


def test_an_unreachable_database_fails_within_the_time_limit_and_is_an_operational_error(monkeypatch):
    monkeypatch.setattr(db, "POOL_TIMEOUT_SECONDS", 1.0)
    started = time.perf_counter()
    with pytest.raises(psycopg.OperationalError):
        with db.db_connection("postgresql://nobody:wrong@127.0.0.1:1/none"):
            pass
    assert 0.8 <= time.perf_counter() - started < 4.0  # n8n gives up at 4 s, so we must answer before that


def test_closing_the_pools_lets_the_next_request_start_a_fresh_one(clean_tables):
    first_pool = db.get_pool(TEST_URL)
    db.close_pools()
    assert first_pool.closed
    with db.db_connection(TEST_URL) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    assert db.get_pool(TEST_URL) is not first_pool


# --- the request path really uses the pool ---------------------------------------------------------

@pytest.mark.parametrize("module", REQUEST_PATH_MODULES)
def test_request_path_modules_no_longer_dial_a_new_connection(module):
    """A leftover connect_with_retry in a request path would quietly keep the 250 ms cost."""
    assert "connect_with_retry" not in (APP / f"{module}.py").read_text(encoding="utf-8")


@pytest.fixture
def web(clean_tables):
    from app.main import app
    make_user()
    client = TestClient(app)
    assert client.post("/login", data={"username": "demo", "password": PASSWORD}).status_code == 200
    return client


def checkouts(action):
    """How many times the pool lent out a connection while `action` ran."""
    pool = db.get_pool(TEST_URL)
    pool.pop_stats()
    action()
    return pool.pop_stats().get("requests_num", 0)


def test_one_dashboard_request_borrows_the_pool_twice_and_never_dials(web):
    # the sign-in check, then the work: two quick loans of the same open connection
    assert checkouts(lambda: web.get("/api/todo")) == 2


def test_the_login_and_the_intake_use_the_pool_too(clean_tables, payload):
    from app.main import app
    make_user()
    anon = TestClient(app)
    assert checkouts(lambda: anon.post("/login", data={"username": "demo", "password": PASSWORD})) >= 1
    from tests.conftest import TEST_API_KEY
    keyed = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    assert checkouts(lambda: keyed.post("/calls", json=payload)) >= 1


def test_the_pools_are_closed_when_the_app_shuts_down(clean_tables):
    from app.main import app
    with TestClient(app) as client:
        client.get("/healthz")
        db.get_pool(TEST_URL)
        assert db._pools
    assert db._pools == {}
