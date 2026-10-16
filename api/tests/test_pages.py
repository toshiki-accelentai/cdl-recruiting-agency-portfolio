"""C2: the HTML pages. FastAPI serves them itself; the page is a shell and the data comes from /api.

Written before the code.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_calls_api import PASSWORD, web  # noqa: F401  (web is a pytest fixture)

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


@pytest.fixture
def anon(clean_tables):
    from app.main import app
    return TestClient(app, follow_redirects=False)


def test_todo_page_sends_a_visitor_to_the_login_page(anon):
    r = anon.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_page_is_public(anon):
    r = anon.get("/login")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert 'name="username"' in r.text and 'name="password"' in r.text


def test_logged_in_user_gets_the_todo_page(web):
    r = web.get("/", follow_redirects=False)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "To do" in r.text


def test_logged_in_user_is_sent_from_login_to_the_todo_page(web):
    r = web.get("/login", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_pages_are_never_cached(anon, web):
    assert anon.get("/login").headers["cache-control"] == "no-store"
    assert web.get("/").headers["cache-control"] == "no-store"


def test_stylesheet_and_scripts_are_served(anon):
    for path in ("/static/app.css", "/static/login.js", "/static/todo.js", "/static/applicant.js", "/static/common.js"):
        r = anon.get(path)
        assert r.status_code == 200, path


def test_static_folder_has_no_directory_listing_or_path_escape(anon):
    assert anon.get("/static/").status_code == 404
    assert anon.get("/static/../main.py").status_code in (404, 400)


@pytest.mark.parametrize("name", ["todo.js", "login.js", "applicant.js", "common.js"])
def test_page_scripts_never_write_html_from_data(name):
    """Names, notes and error text come from callers. innerHTML would let them inject markup."""
    source = (STATIC / name).read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert banned not in source, f"{name} uses {banned}"


def test_no_em_dashes_in_visible_page_text():
    for name in ("login.html", "todo.html", "applicant.html", "login.js", "todo.js", "applicant.js", "common.js", "app.css"):
        assert "—" not in (STATIC / name).read_text(encoding="utf-8"), name


def test_applicant_page_sends_a_visitor_to_the_login_page(anon):
    r = anon.get("/applicants/1")
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_logged_in_user_gets_the_applicant_page_for_any_id(web):
    """The page is a shell; the data call answers 404 for a missing person, and the page says so."""
    r = web.get("/applicants/12345", follow_redirects=False)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-store"


def test_applicant_page_id_must_be_a_number(web):
    assert web.get("/applicants/abc", follow_redirects=False).status_code == 404
