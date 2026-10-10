"""Logging setup shared by the API and the worker (output goes to stderr = `docker logs`)."""
import logging

MAX_ERROR_CHARS = 150


def setup_logging() -> None:
    """Print INFO and above, one line each, with a timestamp. Does nothing if already set up."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def short(text: object, limit: int = MAX_ERROR_CHARS) -> str:
    """Cut an error message so one bad response can never flood the log or leak a whole body."""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."
