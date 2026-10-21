"""Static files: a changed file must reach the browser at once, an unchanged one must not be fetched again.

Pages carry /static/app.css?v=<fingerprint of the file>. A URL with ?v= may be cached for a year (it changes when
the file changes); a URL without it must be revalidated every time. Written before the code.
"""
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import pages
from tests.test_calls_api import web  # noqa: F401  (web is a pytest fixture)

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
VERSIONED = re.compile(r'(?:href|src)="(/static/[A-Za-z0-9_.-]+\.(?:css|js))\?v=([0-9a-f]{10})"')
ANY_ASSET = re.compile(r'(?:href|src)="(/static/[^"]+\.(?:css|js))(\?[^"]*)?"')


@pytest.fixture
def anon(clean_tables):
    from app.main import app
    return TestClient(app)


def fingerprint(name):
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]


# --- the pages ------------------------------------------------------------------------------------

def test_the_login_page_uses_fingerprinted_asset_urls(anon):
    html = anon.get("/login").text
    found = dict(VERSIONED.findall(html))
    assert found == {"/static/app.css": fingerprint("app.css"), "/static/workspace.css": fingerprint("workspace.css"),
                     "/static/login.js": fingerprint("login.js")}


def test_the_todo_page_uses_fingerprinted_asset_urls(web):
    found = dict(VERSIONED.findall(web.get("/").text))
    assert set(found) == {"/static/app.css", "/static/common.js", "/static/todo.js",
                          "/static/workspace.css", "/static/workspace.js", "/static/sections.js",
                          "/static/metrics.js", "/static/analytics.js"}
    assert all(found[name] == fingerprint(name.rsplit("/", 1)[1]) for name in found)


def test_the_applicant_page_uses_fingerprinted_asset_urls(web):
    found = dict(VERSIONED.findall(web.get("/applicants/1").text))
    assert set(found) == {"/static/app.css", "/static/common.js", "/static/applicant.js",
                          "/static/workspace.css", "/static/workspace.js"}


@pytest.mark.parametrize("path", ["/login", "/", "/applicants/1"])
def test_no_page_references_an_asset_without_a_fingerprint(web, path):
    for url, query in ANY_ASSET.findall(web.get(path).text):
        assert query.startswith("?v="), f"{url} has no fingerprint on {path}"


def test_the_pages_themselves_are_still_never_cached(web):
    assert web.get("/").headers["cache-control"] == "no-store"
    assert web.get("/applicants/1").headers["cache-control"] == "no-store"


def test_a_changed_file_gets_a_new_fingerprint(tmp_path):
    (tmp_path / "app.css").write_text("body { color: red }", encoding="utf-8")
    first = pages.static_version("app.css", tmp_path)
    (tmp_path / "app.css").write_text("body { color: blue }", encoding="utf-8")
    second = pages.static_version("app.css", tmp_path)
    assert first != second and len(first) == len(second) == 10


def test_an_unchanged_file_keeps_its_fingerprint(tmp_path):
    (tmp_path / "app.css").write_text("body { color: red }", encoding="utf-8")
    assert pages.static_version("app.css", tmp_path) == pages.static_version("app.css", tmp_path)


# --- the files ------------------------------------------------------------------------------------

def test_a_fingerprinted_url_may_be_kept_for_a_year(anon):
    r = anon.get(f"/static/app.css?v={fingerprint('app.css')}")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_a_plain_url_must_be_checked_again_every_time(anon):
    r = anon.get("/static/app.css")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert r.headers.get("etag")


def test_a_check_for_an_unchanged_file_answers_304_and_keeps_the_rule(anon):
    etag = anon.get("/static/app.css").headers["etag"]
    r = anon.get("/static/app.css", headers={"If-None-Match": etag})
    assert r.status_code == 304 and r.headers["cache-control"] == "no-cache"


def test_a_missing_file_is_404_even_with_a_fingerprint(anon):
    r = anon.get("/static/nope.js?v=0123456789")
    assert r.status_code == 404 and "immutable" not in r.headers.get("cache-control", "")
