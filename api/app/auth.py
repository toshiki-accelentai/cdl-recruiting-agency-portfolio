"""Dashboard login: argon2 password hashes, a signed cookie, two roles.

The cookie carries (user id, session_version). Changing a password bumps session_version, so every
cookie issued earlier stops matching and is rejected: rotating the demo password logs everyone out.
"""
import logging
from typing import Annotated

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import session_cookie_secure, session_secret
from app.db import db_connection
from app.throttle import client_ip, login_throttle, write_throttle

logger = logging.getLogger(__name__)

COOKIE_NAME = "session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
COOKIE_SALT = "dashboard-session"

hasher = PasswordHasher()
# Verified against when the username is unknown, so "no such user" costs the same time as "wrong password".
DUMMY_HASH = hasher.hash("not-a-real-password")

router = APIRouter()


def create_user(conn: psycopg.Connection, username: str, password: str, role: str) -> int:
    return conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
        (username, hasher.hash(password), role),
    ).fetchone()[0]


def change_password(conn: psycopg.Connection, username: str, new_password: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = %s, session_version = session_version + 1 WHERE username = %s",
        (hasher.hash(new_password), username),
    )


def check_password(conn: psycopg.Connection, username: str, password: str) -> dict | None:
    row = conn.execute(
        "SELECT id, username, role, session_version, password_hash FROM users WHERE username = %s",
        (username,),
    ).fetchone()
    stored = row[4] if row else DUMMY_HASH
    try:
        hasher.verify(stored, password)
    except VerifyMismatchError:
        return None
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "role": row[2], "session_version": row[3]}


def _serializer() -> URLSafeTimedSerializer:
    secret = session_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="session secret not configured")
    return URLSafeTimedSerializer(secret, salt=COOKIE_SALT)


def current_user(request: Request) -> dict:
    """The logged-in user, or 401. Every dashboard endpoint depends on this."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="not logged in")
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:  # tampered, wrong key, or older than SESSION_MAX_AGE_SECONDS
        raise HTTPException(status_code=401, detail="not logged in")
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role, session_version FROM users WHERE id = %s", (data["u"],)
        ).fetchone()
    if row is None or row[3] != data["v"]:
        raise HTTPException(status_code=401, detail="not logged in")
    return {"id": row[0], "username": row[1], "role": row[2]}


def require_writer(user: Annotated[dict, Depends(current_user)]) -> dict:
    """Dependency for the write endpoints: a recruiter or admin who is not writing too fast (else 429)."""
    if user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="not allowed")
    wait = write_throttle.hit(user["id"])
    if wait:
        raise HTTPException(status_code=429, detail="too many changes too fast; wait a moment",
                            headers={"Retry-After": str(wait)})
    return user


def require_role(*roles: str):
    """Dependency: logged in AND holding one of `roles`, else 403."""
    def check(user: Annotated[dict, Depends(current_user)]) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="not allowed")
        return user
    return check


@router.post("/login")
def login(request: Request, response: Response, username: Annotated[str, Form()], password: Annotated[str, Form()]):
    serializer = _serializer()  # 503 before touching the database if no secret is configured
    address = client_ip(request)
    wait = login_throttle.blocked_for(address, username)
    if wait:  # checked before the password, so a blocked guesser also costs us no password hashing
        logger.warning("login throttled")
        raise HTTPException(status_code=429, detail="too many sign-in attempts, try again later",
                            headers={"Retry-After": str(wait)})
    with db_connection() as conn:
        user = check_password(conn, username, password)
    if user is None:
        login_throttle.record_failure(address, username)
        logger.warning("login failed")  # never log the username or password typed
        raise HTTPException(status_code=401, detail="invalid username or password")
    login_throttle.record_success(address, username)
    token = serializer.dumps({"u": user["id"], "v": user["session_version"]})
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_MAX_AGE_SECONDS, httponly=True,
                        samesite="lax", secure=session_cookie_secure())
    logger.info("login ok user_id=%s role=%s", user["id"], user["role"])
    return {"username": user["username"], "role": user["role"]}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/api/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return {"username": user["username"], "role": user["role"]}
