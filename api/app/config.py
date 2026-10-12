import os

DEFAULT_DATABASE_URL = "postgresql://cdl:cdl@localhost:5433/cdl"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def api_shared_secret() -> str:
    """The key n8n must send in X-API-Key. Empty string = not configured."""
    return os.environ.get("API_SHARED_SECRET", "")
