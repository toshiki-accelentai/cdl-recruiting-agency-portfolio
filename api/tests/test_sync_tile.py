"""The "Zoho sync issues" tile counts a Zoho outage, not only rows that gave up (owner request 2026-10-29).

During an outage a row never fails: it stays pending and the worker retries with a growing wait. So the tile counts
  - failed rows, and
  - pending rows that have already been tried at least once (they are retrying because Zoho did not answer).
A fresh pending row (attempts 0) is normal for a few seconds after every call and is NOT an issue. Written before the code.
"""
from pathlib import Path

from tests.test_calls_api import add_call, ids, web  # noqa: F401  (web is a pytest fixture)

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def seed(web):
    failed = add_call(name="Failed", phone="+12065550231", outbox={"status": "failed", "attempts": 3})
    retrying = add_call(name="Retrying", phone="+12065550232", outbox={"status": "pending", "attempts": 4, "last_error": "network error"})
    fresh = add_call(name="Fresh", phone="+12065550233", outbox={"status": "pending", "attempts": 0})
    sent = add_call(name="Sent", phone="+12065550234", outbox={"status": "sent", "attempts": 1})
    add_call(name="No outbox", phone="+12065550235")
    return failed, retrying, fresh, sent


def test_tile_counts_failed_and_retrying_rows_only(web):
    seed(web)
    assert web.get("/api/todo").json()["summary"]["sync_problems"] == 2


def test_an_outage_with_nothing_failed_still_shows_one(web):
    add_call(name="Morgan", phone="+12065550236", outbox={"status": "pending", "attempts": 3, "last_error": "network error"})
    assert web.get("/api/todo").json()["summary"]["sync_problems"] == 1


def test_a_fresh_pending_row_is_not_an_issue(web):
    add_call(name="Just called", phone="+12065550237", outbox={"status": "pending", "attempts": 0})
    assert web.get("/api/todo").json()["summary"]["sync_problems"] == 0


def test_the_list_behind_the_tile_has_the_same_rows_as_its_count(web):
    failed, retrying, fresh, sent = seed(web)
    page = web.get("/api/calls?sync=problem").json()
    assert sorted(i["id"] for i in page["items"]) == sorted([failed, retrying])
    assert page["total"] == web.get("/api/todo").json()["summary"]["sync_problems"]


def test_the_existing_sync_filters_are_unchanged(web):
    failed, retrying, fresh, sent = seed(web)
    assert ids(web.get("/api/calls?sync=failed")) == [failed]
    assert sorted(ids(web.get("/api/calls?sync=pending"))) == sorted([retrying, fresh])
    assert ids(web.get("/api/calls?sync=sent")) == [sent]


def test_an_unknown_sync_value_is_rejected(web):
    assert web.get("/api/calls?sync=broken").status_code == 422


def test_the_tile_links_to_the_problem_list():
    assert 'href="/#activity?sync=problem"' in (STATIC / "todo.html").read_text(encoding="utf-8")


def test_the_activity_page_offers_the_problem_filter():
    page = (STATIC / "todo.html").read_text(encoding="utf-8")
    assert 'value="problem"' in page.split('id="activity-sync"')[1].split("</select>")[0]
