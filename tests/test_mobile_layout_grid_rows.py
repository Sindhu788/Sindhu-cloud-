"""2026-09-14 fix: the mobile (max-width: 768px) .app-shell rule used to
override grid-template-areas to a 2-row layout ("topbar" "content")
without also overriding grid-template-rows, which the base rule still
sets to 3 explicit tracks (60px var(--banner-h) 1fr). With a row-count
mismatch between grid-template-areas and grid-template-rows, "content"
silently landed in the banner's own near-zero-height track instead of
the real 1fr track -- clamping the entire main content area on mobile to
a sliver a few dozen pixels tall on every page. Confirmed live (via
computed-style measurement in a real rendered page) before and after
this fix.

This is a pure-CSS bug with no Python-level runtime to exercise, so this
guard parses app.css directly and asserts the one invariant that caused
the regression: the mobile override's grid-template-areas must declare
the same number of rows as the base rule's grid-template-rows, so
"content" always lands in the real 1fr track, not an implicit/foreign
one.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_css():
    css_path = _REPO_ROOT / "sindhu_web" / "static" / "css" / "app.css"
    return css_path.read_text(encoding="utf-8")


def _grid_template_rows_track_count(declaration_value):
    # A crude but sufficient track counter for this file's own syntax:
    # space-separated tokens, each either a length (60px), a var(), or a
    # flex unit (1fr) -- exactly what .app-shell uses, nothing fancier.
    return len(declaration_value.split())


def _grid_template_areas_row_count(declaration_value):
    # Each quoted string in a grid-template-areas value is one row.
    return len(re.findall(r'"[^"]*"', declaration_value))


def test_base_app_shell_rows_and_areas_agree():
    css = _read_css()
    base_rule = re.search(
        r"\.app-shell\s*\{[^}]*grid-template-rows:\s*([^;]+);[^}]*grid-template-areas:\s*([^;]+);",
        css, re.DOTALL,
    )
    assert base_rule, "could not find the base .app-shell grid-template-rows/areas declarations"
    rows = _grid_template_rows_track_count(base_rule.group(1))
    areas = _grid_template_areas_row_count(base_rule.group(2))
    assert rows == areas, (
        f"base .app-shell defines {rows} row track(s) but grid-template-areas "
        f"declares {areas} row(s) -- a grid item will silently land in the "
        f"wrong track"
    )


def test_mobile_app_shell_override_keeps_row_count_in_sync():
    css = _read_css()
    mobile_block = re.search(r"@media \(max-width: 768px\) \{(.*?)\n\}\n", css, re.DOTALL)
    assert mobile_block, "could not find the @media (max-width: 768px) block"
    mobile_rule = re.search(
        r"\.app-shell,\s*\.app-shell\.rail-collapsed\s*\{([^}]+)\}",
        mobile_block.group(1), re.DOTALL,
    )
    assert mobile_rule, "could not find the mobile .app-shell override rule"
    areas_match = re.search(r"grid-template-areas:\s*([^;]+);", mobile_rule.group(1))
    assert areas_match, "mobile .app-shell override no longer sets grid-template-areas"
    mobile_areas_rows = _grid_template_areas_row_count(areas_match.group(1))

    rows_match = re.search(r"grid-template-rows:\s*([^;]+);", mobile_rule.group(1))
    if rows_match:
        # If a future change starts overriding grid-template-rows here too,
        # it must still agree with the areas row count.
        mobile_rows = _grid_template_rows_track_count(rows_match.group(1))
    else:
        # Not overridden here -- the base rule's 3-track grid-template-rows
        # still applies (this is the actual fix: keep the SAME 3 rows,
        # just one column), so the areas override must also declare 3 rows.
        base_rows_match = re.search(r"\.app-shell\s*\{[^}]*grid-template-rows:\s*([^;]+);", css, re.DOTALL)
        mobile_rows = _grid_template_rows_track_count(base_rows_match.group(1))

    assert mobile_rows == mobile_areas_rows, (
        f"mobile .app-shell override declares {mobile_areas_rows} row(s) in "
        f"grid-template-areas but {mobile_rows} row track(s) are actually in "
        f"effect -- 'content' will silently land in the wrong track and get "
        f"clamped to a sliver, exactly the 2026-09-14 mobile bug this guards "
        f"against"
    )
    assert '"content"' in areas_match.group(1), "mobile grid-template-areas must still place 'content' in its own row"
