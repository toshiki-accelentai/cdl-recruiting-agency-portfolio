import os

DEFAULT_DATABASE_URL = "postgresql://cdl:cdl@localhost:5433/cdl"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def session_secret() -> str:
    """Signs the login cookie. Empty string = not configured, and login then answers 503."""
    return os.environ.get("SESSION_SECRET", "")


MIN_SESSION_SECRET_LENGTH = 32  # shorter than this is treated as "not configured"


def instance_name() -> str:
    """Which deployment this is ("demo", "real"). Part of what the cookie is signed with, so a cookie made by one
    instance is worthless on another even if they were given the same secret by mistake. Empty = the default."""
    return os.environ.get("INSTANCE_NAME", "")


def demo_config_problem() -> str | None:
    """Why this server must not start as a demo, or None. The demo never holds the n8n key or the VAPI key."""
    if os.environ.get("DEMO_MODE") != "1":
        return None
    held = [name for name in ("API_SHARED_SECRET", "VAPI_PRIVATE_KEY") if os.environ.get(name)]
    if held:
        return "DEMO_MODE=1 but " + " and ".join(held) + " is set: the demo must not hold real keys"
    return None


def session_cookie_secure() -> bool:
    """Secure cookies are sent over HTTPS only. On by default; local HTTP dev sets it to 0."""
    return os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"


def api_shared_secret() -> str:
    """The key n8n must send in X-API-Key. Empty string = not configured."""
    return os.environ.get("API_SHARED_SECRET", "")


def vapi_private_key() -> str:
    """Lets the API ask VAPI for a signed recording link. Empty string = not configured."""
    return os.environ.get("VAPI_PRIVATE_KEY", "")
