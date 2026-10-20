"""Database connections for the API.

Requests borrow a connection from a small pool (db_connection). Opening a fresh connection to Supabase costs
about 250 ms (around 8 round trips), so the pool keeps a few open and lends them out. connect_with_retry stays
for the command-line tool, which makes one short-lived connection.
"""
import logging
import threading
import time
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

from app.config import database_url
from app.logs import short

logger = logging.getLogger(__name__)

RETRY_WAITS = (0.5, 1.0)  # seconds to wait after the 1st and 2nd failed try: 3 tries, ~1.5s of waiting


def connect_with_retry(url: str, connect=psycopg.connect, sleep=time.sleep) -> psycopg.Connection:
    """Open a connection, retrying a short outage (DNS blip, pooler restart).

    Only OperationalError is retried: it means "could not reach the database right now".
    A bad connection string or a programming error would fail every time, so it is raised at once.
    After the last try the original error is raised, so the caller can still answer "not saved".
    """
    tries = len(RETRY_WAITS) + 1
    for number, wait in enumerate(RETRY_WAITS, start=1):
        try:
            return connect(url)
        except psycopg.OperationalError as exc:
            logger.warning("database connect failed (try %d/%d): %s", number, tries, short(exc))
            sleep(wait)
    return connect(url)


POOL_MIN_SIZE = 1                 # always keep one connection ready
POOL_MAX_SIZE = 4                 # never more: Supabase limits how many connections can be open
POOL_TIMEOUT_SECONDS = 3.0        # how long a request waits for a free connection; n8n gives up at 4 s
POOL_MAX_IDLE_SECONDS = 300       # connections above the minimum are closed after this long unused
POOL_MAX_LIFETIME_SECONDS = 1800  # connections are replaced after this long, so none gets old and stale
CONNECT_TIMEOUT_SECONDS = 10

_pools: dict[str, ConnectionPool] = {}
_pools_lock = threading.Lock()


def get_pool(url: str) -> ConnectionPool:
    """The pool for this database address, created on first use."""
    pool = _pools.get(url)
    if pool is None:
        with _pools_lock:
            pool = _pools.get(url)
            if pool is None:
                pool = ConnectionPool(
                    url, min_size=POOL_MIN_SIZE, max_size=POOL_MAX_SIZE, timeout=POOL_TIMEOUT_SECONDS,
                    max_idle=POOL_MAX_IDLE_SECONDS, max_lifetime=POOL_MAX_LIFETIME_SECONDS,
                    check=ConnectionPool.check_connection,  # a connection the server dropped is replaced before use
                    kwargs={"connect_timeout": CONNECT_TIMEOUT_SECONDS}, name="cdl-api", open=False)
                pool.open(wait=False)  # connect in the background; the first request waits only if it must
                _pools[url] = pool
    return pool


@contextmanager
def db_connection(url: str | None = None):
    """Borrow a connection: committed on success, rolled back on error, then handed back (not closed)."""
    try:
        with get_pool(url or database_url()).connection() as conn:
            yield conn
    except PoolTimeout as exc:  # a subclass of OperationalError, so callers handle it like any outage
        logger.warning("no database connection available within %.0f s: %s", POOL_TIMEOUT_SECONDS, short(exc))
        raise


def close_pools() -> None:
    """Close every pool (on shutdown, and between tests)."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close()
