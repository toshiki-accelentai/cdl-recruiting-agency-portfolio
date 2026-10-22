"""UI redesign guards (owner review 2026-10-21): readable text, one font, one palette, real icons, a centered login.

These read the static files only. They cannot judge looks; they stop the specific problems the owner found from
coming back. Written before the code.
"""
import re
from pathlib import Path

import pytest

from tests.test_pages import anon  # noqa: F401  (anon is a pytest fixture)

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
CSS_FILES = ("app.css", "workspace.css")
PAGES = ("login.html", "todo.html", "applicant.html")
MIN_TEXT_PX = 12
OLD_GOLD = ("#ecd9ac", "#f0dfbb", "#eadab9", "#d8b775", "#e2d9fb")  # the gold edges that clashed with the purple
SYMBOL_GLYPHS = ("▦", "♙", "▥", "⌕")  # text characters that stood in for icons


def css(name):
    return (STATIC / name).read_text(encoding="utf-8")


def rule(source, selector):
    """The declarations of the first top-level rule whose selector list is exactly `selector`."""
    match = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", source, re.MULTILINE)
    return match.group(1) if match else ""


@pytest.mark.parametrize("name", CSS_FILES)
def test_no_text_is_smaller_than_12px(name):
    sizes = [float(px) for px in re.findall(r"font-size:\s*([\d.]+)px", css(name))]
    sizes += [float(rem) * 16 for rem in re.findall(r"font-size:\s*([\d.]+)rem", css(name))]
    assert sizes, f"{name} sets no font sizes"
    assert min(sizes) >= MIN_TEXT_PX, f"{name} has text at {min(sizes)}px"


def test_one_font_inter_is_bundled_and_served(anon):
    assert "InterVariable.woff2" in css("workspace.css")
    assert anon.get("/static/InterVariable.woff2").status_code == 200
    assert (STATIC / "Inter-OFL.txt").exists()  # the font license travels with the font


def test_the_old_font_is_gone():
    assert not (STATIC / "Manrope-Variable.ttf").exists()
    for name in CSS_FILES:
        assert "Manrope" not in css(name), name


def test_buttons_never_show_a_link_underline():
    """'Review applicant' is a link styled as a button; the browser's underline must not show."""
    assert re.search(r"text-decoration:\s*none", rule(css("app.css"), ".btn"))


@pytest.mark.parametrize("name", CSS_FILES)
def test_the_clashing_gold_edges_are_gone(name):
    source = css(name).lower()
    for color in OLD_GOLD:
        assert color not in source, f"{name} still uses {color}"


@pytest.mark.parametrize("name", PAGES)
def test_every_page_uses_the_shared_design(name):
    html = (STATIC / name).read_text(encoding="utf-8")
    assert "/static/workspace.css" in html, name


def test_login_card_is_centered():
    login = rule(css("workspace.css"), ".auth-main")
    assert re.search(r"place-items:\s*center|justify-content:\s*center", login)


@pytest.mark.parametrize("name", ("todo.html", "applicant.html"))
def test_navigation_uses_svg_icons_not_symbol_characters(name):
    html = (STATIC / name).read_text(encoding="utf-8")
    assert "<svg" in html
    for glyph in SYMBOL_GLYPHS:
        assert glyph not in html, f"{name} still uses {glyph}"


@pytest.mark.parametrize("name", ("todo.html", "applicant.html"))
def test_no_small_caps_labels_above_every_heading(name):
    """Too much small text: the eyebrow labels repeated what the heading already said."""
    assert 'class="eyebrow"' not in (STATIC / name).read_text(encoding="utf-8")


def test_motion_stops_for_people_who_ask_for_less():
    assert "prefers-reduced-motion" in css("workspace.css")


def test_open_in_the_applicant_table_is_a_button_without_an_underline():
    """Owner review 2026-10-22: 'Open' looked like link text and underlined on hover."""
    script = (STATIC / "sections.js").read_text(encoding="utf-8")
    assert re.search(r'cls: "btn btn-sm table-open"', script)
    for selector in (".app-body .table-open", ".app-body .table-open:hover"):
        assert rule(css("workspace.css"), selector), f"no rule for {selector}"
        assert "underline" not in rule(css("workspace.css"), selector), selector


LOGO = "frontline-cdl-logo.svg"
MARK = "frontline-cdl-mark.svg"


@pytest.mark.parametrize("name", (LOGO, MARK))
def test_logo_svgs_are_self_contained_vectors(name):
    """Approved logo handoff 2026-10-22: outlined paths only, so no font, image, script or outside file is needed."""
    svg = (STATIC / name).read_text(encoding="utf-8")
    assert re.search(r'<svg[^>]*viewBox="0 0 \d+ \d+"', svg)
    for banned in ("<image", "<text", "<script", "<style", "<filter", "href=", "url(", "@import"):
        assert banned not in svg, f"{name} contains {banned}"
    assert svg.count("<path") >= 2


@pytest.mark.parametrize("name", PAGES)
def test_every_page_shows_the_approved_logo(name):
    html = (STATIC / name).read_text(encoding="utf-8")
    logo = re.search(r'<img class="brand-logo" src="/static/' + re.escape(LOGO) + r'" width="1894" height="319" alt="Frontline CDL">', html)
    assert logo, f"{name} lacks the full logo with its real size and alt text"
    assert 'class="brand-mark"' not in html, f"{name} still has the placeholder F tile"


@pytest.mark.parametrize("name", ("todo.html", "applicant.html"))
def test_the_collapsed_sidebar_swaps_to_the_symbol(name):
    html = (STATIC / name).read_text(encoding="utf-8")
    assert re.search(r'<img class="brand-symbol" src="/static/' + re.escape(MARK) + r'" width="433" height="433" alt="Frontline CDL">', html)
    workspace = css("workspace.css")
    assert "brand-mark" not in workspace
    assert "display: none" in rule(workspace, ".brand-symbol")  # hidden while the full logo fits
    narrow = re.search(r"@media \(max-width: 1024px\) \{(.*?)\n\}", workspace, re.DOTALL).group(1)
    assert re.search(r"\.brand-logo[^{]*\{[^}]*display:\s*none", narrow)
    assert re.search(r"\.brand-symbol\s*\{[^}]*display:\s*block", narrow)


def test_only_the_sidebar_logo_collapses_the_login_logo_never_hides():
    """Found in the browser check: an unscoped '.brand-logo { display: none }' at 1024px blanked the login logo."""
    narrow = re.search(r"@media \(max-width: 1024px\) \{(.*?)\n\}", css("workspace.css"), re.DOTALL).group(1)
    for selector in re.findall(r"([^{}]*)\{[^}]*display:\s*none", narrow):
        if "brand-logo" in selector:
            assert ".sidebar .brand-logo" in selector, selector


def test_logo_keeps_its_aspect_ratio_and_never_overflows():
    for selector in (".brand-logo", ".brand-symbol"):
        declarations = rule(css("workspace.css"), selector)
        assert "height: auto" in declarations and "max-width: 100%" in declarations, selector


@pytest.mark.parametrize("name", PAGES)
def test_the_tab_icon_is_the_approved_symbol(name):
    html = (STATIC / name).read_text(encoding="utf-8")
    assert f'rel="icon" type="image/svg+xml" href="/static/{MARK}"' in html
    assert 'href="data:' not in html, f"{name} still has the old inline placeholder icon"


def test_call_activity_search_sits_in_the_filter_toolbar():
    """Owner review 2026-10-22: the search box was stuck to the panel edge on a row of its own."""
    script = (STATIC / "sections.js").read_text(encoding="utf-8")
    assert 'querySelector(".activity-toolbar").appendChild(activitySearchWrap)' in script
