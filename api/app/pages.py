"""The recruiter pages. Each page is a static HTML shell; its script fetches the data from /api.

A visitor without a valid session is redirected to the login page here, before any page is sent.

Assets are linked as /static/app.css?v=<fingerprint of the file>. The fingerprint changes when the file changes,
so a URL with it may be cached for a year (no request at all on the next visit), and a deploy reaches every
browser at once. A URL without it must be checked again every time (the file may have changed).
"""
import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import current_user

STATIC_DIR = Path(__file__).resolve().parent / "static"
NO_STORE = {"Cache-Control": "no-store"}  # a page must never be shown from cache after logout
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"  # "may keep it, but ask first": answered 304 when unchanged
FINGERPRINT_LENGTH = 10
ASSET_REFERENCE = re.compile(r'(/static/([A-Za-z0-9_.-]+\.(?:css|js)))(?=")')

_fingerprints: dict[tuple[str, int, int], str] = {}


def static_version(name: str, directory: Path = STATIC_DIR) -> str:
    """A short fingerprint of the file's content; recomputed only when the file's time or size changes."""
    path = directory / name
    info = path.stat()
    key = (str(path), info.st_mtime_ns, info.st_size)
    if key not in _fingerprints:
        _fingerprints[key] = hashlib.sha256(path.read_bytes()).hexdigest()[:FINGERPRINT_LENGTH]
    return _fingerprints[key]


def page_response(name: str) -> HTMLResponse:
    html = (STATIC_DIR / name).read_text(encoding="utf-8")
    html = ASSET_REFERENCE.sub(lambda m: f"{m.group(1)}?v={static_version(m.group(2))}", html)
    return HTMLResponse(html, headers=NO_STORE)


class FingerprintedStaticFiles(StaticFiles):
    """Static files that say how long they may be kept, depending on whether the URL carries a fingerprint."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            response.headers["Cache-Control"] = IMMUTABLE if query.get("v") else REVALIDATE
        return response


router = APIRouter()
static_files = FingerprintedStaticFiles(directory=STATIC_DIR)


def logged_in(request: Request) -> bool:
    try:
        current_user(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return False
        raise
    return True


@router.get("/", include_in_schema=False)
def todo_page(request: Request):
    if not logged_in(request):
        return RedirectResponse("/login", status_code=303, headers=NO_STORE)
    return page_response("todo.html")


@router.get("/applicants/{applicant_id:int}", include_in_schema=False)  # ":int" so "abc" is a plain 404
def applicant_page(applicant_id: int, request: Request):
    if not logged_in(request):
        return RedirectResponse("/login", status_code=303, headers=NO_STORE)
    return page_response("applicant.html")


@router.get("/login", include_in_schema=False)
def login_page(request: Request):
    if logged_in(request):
        return RedirectResponse("/", status_code=303, headers=NO_STORE)
    return page_response("login.html")
