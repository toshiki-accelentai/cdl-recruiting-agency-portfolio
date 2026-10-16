"""The recruiter pages. Each page is a static HTML shell; its script fetches the data from /api.

A visitor without a valid session is redirected to the login page here, before any page is sent.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import current_user

STATIC_DIR = Path(__file__).resolve().parent / "static"
NO_STORE = {"Cache-Control": "no-store"}  # a page must never be shown from cache after logout

router = APIRouter()
static_files = StaticFiles(directory=STATIC_DIR)


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
    return FileResponse(STATIC_DIR / "todo.html", headers=NO_STORE)


@router.get("/applicants/{applicant_id:int}", include_in_schema=False)  # ":int" so "abc" is a plain 404
def applicant_page(applicant_id: int, request: Request):
    if not logged_in(request):
        return RedirectResponse("/login", status_code=303, headers=NO_STORE)
    return FileResponse(STATIC_DIR / "applicant.html", headers=NO_STORE)


@router.get("/login", include_in_schema=False)
def login_page(request: Request):
    if logged_in(request):
        return RedirectResponse("/", status_code=303, headers=NO_STORE)
    return FileResponse(STATIC_DIR / "login.html", headers=NO_STORE)
