import os

DEFAULT_DATABASE_URL = "postgresql://cdl:cdl@localhost:5433/cdl"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def session_secret() -> str:
    """Signs the login cookie. Empty string = not configured, and login then answers 503."""
    return os.environ.get("SESSION_SECRET", "")


def session_cookie_secure() -> bool:
    """Secure cookies are sent over HTTPS only. On by default; local HTTP dev sets it to 0."""
    return os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"


def api_shared_secret() -> str:
    """The key n8n must send in X-API-Key. Empty string = not configured."""
    return os.environ.get("API_SHARED_SECRET", "")


def vapi_private_key() -> str:
    """Lets the API ask VAPI for a signed recording link. Empty string = not configured."""
    return os.environ.get("VAPI_PRIVATE_KEY", "")
