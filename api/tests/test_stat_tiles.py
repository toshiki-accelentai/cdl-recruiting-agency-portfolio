"""The four numbers on the Overview open a filtered view (owner request 2026-10-26). Written before the code.

 Calls today        -> Call activity, day=today            (needs the API to filter calls by business day)
 Awaiting contact   -> Applicants, status=to_call
 High readiness     -> Applicants, status=to_call and readiness=hot
 Zoho sync issues   -> Call activity, sync=problem (failed or retrying; see test_sync_tile.py)
"""
import re
from pathlib import Path

import pytest

from tests.test_calls_api import add_call, web  # noqa: F401  (web is a pytest fixture)

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def ids(response):
    return [item["id"] for item in response.json()["items"]]


# --- API: calls of today (Vancouver business day) ---------------------------------------------------------

def test_day_today_lists_only_todays_calls(web):
    today = add_call(name="Today Caller", phone="+12065550141", minutes_ago=0)
    add_call(name="Old Caller", phone="+12065550142", minutes_ago=3 * 24 * 60)
    r = web.get("/api/calls?day=today")
    assert r.status_code == 200
    assert ids(r) == [today] and r.json()["total"] == 1


def test_the_count_on_the_tile_equals_the_filtered_list(web):
    add_call(name="A", phone="+12065550143", minutes_ago=0)
    add_call(name="B", phone="+12065550144", minutes_ago=1)
    add_call(name="C", phone="+12065550145", minutes_ago=5 * 24 * 60)
    tile = web.get("/api/todo").json()["summary"]["calls_today"]
    assert web.get("/api/calls?day=today").json()["total"] == tile


def test_day_combines_with_the_other_filters(web):
    failed = add_call(name="F", phone="+12065550146", minutes_ago=0, outbox={"status": "failed"})
    add_call(name="S", phone="+12065550147", minutes_ago=0, outbox={"status": "sent"})
    add_call(name="Old failed", phone="+12065550148", minutes_ago=4 * 24 * 60, outbox={"status": "failed"})
    assert ids(web.get("/api/calls?day=today&sync=failed")) == [failed]


def test_only_today_is_an_accepted_day(web):
    assert web.get("/api/calls?day=yesterday").status_code == 422


def test_without_day_nothing_changes(web):
    add_call(name="A", phone="+12065550149", minutes_ago=0)
    add_call(name="B", phone="+12065550150", minutes_ago=3 * 24 * 60)
    assert web.get("/api/calls").json()["total"] == 2


# --- the page ---------------------------------------------------------------------------------------------

def html():
    return (STATIC / "todo.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("target", ["/#activity?day=today", "/#applicants?status=needs_contact",
                                    "/#applicants?status=needs_contact&amp;readiness=hot", "/#activity?sync=problem"])
def test_each_tile_links_to_its_filtered_view(target):
    summary = html().split('id="summary"')[1].split("</section>")[0]
    assert f'href="{target}"' in summary, target


def test_the_tiles_have_exactly_four_distinct_targets():
    summary = html().split('id="summary"')[1].split("</section>")[0]
    assert len(set(re.findall(r'href="([^"]+)"', summary))) == 4


def test_applicants_has_a_readiness_filter_and_activity_has_a_day_filter():
    page = html()
    assert 'id="applicant-readiness"' in page
    for value in ("hot", "medium", "warm", "cold"):
        assert f'value="{value}"' in page.split('id="applicant-readiness"')[1].split("</select>")[0]
    assert 'id="activity-day"' in page and 'value="today"' in page.split('id="activity-day"')[1].split("</select>")[0]


def test_the_page_scripts_read_the_link_filters():
    assert "/static/route_filters.js" in html()
    assert "routeFilters" in (STATIC / "workspace.js").read_text(encoding="utf-8")
    sections = (STATIC / "sections.js").read_text(encoding="utf-8")
    assert "event.detail.params" in sections and "applicant-readiness" in sections and "activity-day" in sections


def test_the_applicants_page_has_the_same_needs_contact_filter_as_the_overview():
    """The Overview counts people with status To contact PLUS people who called again since the last update.
    The tile and the list it opens must use the same definition, or the numbers disagree (found 2026-10-26)."""
    page = html()
    assert 'data-status="needs_contact"' in page
    sections = (STATIC / "sections.js").read_text(encoding="utf-8")
    assert "needs_contact" in sections and "new_call_since" in sections
