"""Database connection helper for the API."""
import logging
import time

import psycopg

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
