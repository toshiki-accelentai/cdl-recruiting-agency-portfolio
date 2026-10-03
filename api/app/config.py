import os

DEFAULT_DATABASE_URL = "postgresql://cdl:cdl@localhost:5433/cdl"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
