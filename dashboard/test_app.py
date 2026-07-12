"""
Automated logic checks for the Career Dashboard, via Streamlit's built-in
st.testing.v1.AppTest (headless, no browser) -- per the user's explicit
testing-approach decision for Phase 6. Run directly: python3
dashboard/test_app.py (or via pytest if ever added to this project).
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from streamlit.testing.v1 import AppTest

APP_PATH = str(pathlib.Path(__file__).resolve().parent / "app.py")
DASHBOARD_DIR = str(pathlib.Path(__file__).resolve().parent)


def _page_apptest(module_name, call_with_dummy_pages=False):
    """AppTest.from_function only serializes the function's own bytecode,
    not its enclosing module's imports (confirmed: calling a page's
    render() this way raised NameError on every name the module imports
    at module level, e.g. get_connections) -- so this writes a tiny real
    script instead, the same mechanism app.py itself already uses
    reliably via AppTest.from_file. call_with_dummy_pages: True for the
    3 page modules whose render() takes (self_page, detail_page) -- safe
    to pass None for a bare render with no row/button click simulated."""
    call = "render(None, None)" if call_with_dummy_pages else "render()"
    script = (f"import sys\nsys.path.insert(0, {DASHBOARD_DIR!r})\n"
              f"import {module_name}\nfrom {module_name} import render\n{call}\n")
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    tmp.write(script)
    tmp.close()
    return AppTest.from_file(tmp.name)


def test_app_runs_without_exception():
    """AppTest.from_file always renders the DEFAULT page (Overview, per
    app.py's st.Page(..., default=True)) -- this only ever exercises that
    one page, not the other 5. See test_all_career_pages_render below for
    the rest."""
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    assert not at.exception, f"App raised: {at.exception}"


def test_all_career_pages_render():
    """Phase 6c.4 replaces the old 9-tab single page with 6 separate
    pages. AppTest.from_file can only ever render app.py's DEFAULT page
    (confirmed in 6c.3: AppTest.switch_page needs a real file path,
    which function-based pages don't have) -- so each page's render()
    is exercised directly via a tiny generated script (see
    _page_apptest), bypassing st.navigation entirely. None is passed for
    the page-link args (self_page/detail_page): those are only touched
    if a row/button is actually clicked, which doesn't happen in a bare
    .run()."""
    no_arg_pages = ["patterns_view", "openings_view", "game_endings_view"]
    two_arg_pages = ["overview_view", "matchups_view", "tactical_highlights_view"]

    for module_name in no_arg_pages:
        at = _page_apptest(module_name)
        at.run(timeout=60)
        assert not at.exception, f"{module_name} raised: {at.exception}"

    for module_name in two_arg_pages:
        at = _page_apptest(module_name, call_with_dummy_pages=True)
        at.run(timeout=60)
        assert not at.exception, f"{module_name} raised: {at.exception}"


def test_openings_min_games_filter_changes_row_count():
    """Drives openings_view.render() directly -- the "Minimum games"
    slider now lives on its own page (Openings & Repertoire), not the
    default page AppTest.from_file(APP_PATH) renders."""
    at = _page_apptest("openings_view")
    at.run(timeout=60)
    sliders = [s for s in at.slider if s.label == "Minimum games"]
    assert sliders, "Minimum games slider not found"
    slider = sliders[0]

    slider.set_value(1).run(timeout=60)
    dataframes_low = at.dataframe
    assert dataframes_low, "No dataframe rendered with min_games=1"
    n_rows_low = len(dataframes_low[0].value)

    slider.set_value(50).run(timeout=60)
    dataframes_high = at.dataframe
    n_rows_high = len(dataframes_high[0].value)

    assert n_rows_low >= n_rows_high, (
        f"Raising the min-games filter should never increase row count "
        f"(got {n_rows_low} at min=1, {n_rows_high} at min=50)")


def test_headline_metrics_match_known_values():
    """Cross-check against the live database via direct SQL, not a
    hardcoded literal -- since Phase 7 (sync.py), the real game count
    changes every time the user syncs, so a fixed expected value would
    go stale and need editing after every sync. Confirms the app surfaces
    whatever data.py actually produced, not a frozen historical snapshot."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from _common import resolve_db_path, get_sqlite_connection

    conn = get_sqlite_connection(resolve_db_path())
    real_total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    metric_values = {m.label: m.value for m in at.metric}
    assert metric_values["Total games"] == f"{real_total:,}"


def test_game_explorer_badge_filter_reduces_row_count():
    """Tested directly through data.py rather than by driving the Game
    Explorer page's UI: since Phase 6c.3's multi-page restructure
    (st.navigation/st.Page with function-based pages, not file-based),
    AppTest.switch_page requires an actual file path -- function-based
    pages have none, confirmed by inspecting the error
    ("make sure the page given is relative to the main script"). Same
    class of confirmed AppTest limitation as the earlier dataframe
    row-click gap (see test_narrative_is_deterministic_for_the_same_game)
    -- not workaround-able, so exercise the actual filtering logic
    directly instead."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from _common import resolve_db_path, get_duckdb_connection
    import data

    conn = get_duckdb_connection(resolve_db_path())
    explorer_df = data.get_game_explorer_table(conn)
    filtered = explorer_df[explorer_df.is_comeback]
    assert len(filtered) > 0, "No comeback-badged games found -- filter logic itself may be broken"
    # Comeback is the rarest badge -- filtering on it should shrink the
    # table dramatically from the full population.
    assert len(filtered) < len(explorer_df) * 0.05


def test_opening_and_opponent_commentary_buttons_render_correctly():
    """Per-opening (Openings & Repertoire) and per-opponent (Matchups &
    Opponents) commentary buttons, disabled when no API key is configured
    anywhere (keyring / plaintext fallback / env var -- see
    api_key_store.get_api_key()). No real API call here -- this only
    checks the buttons render and their disabled state matches whether a
    key is actually available in this environment (presence-only check,
    never the value itself). Label is "Generate..." or "Regenerate..."
    depending on whether claude_narratives already has a cached row for
    whichever subject happens to be selected by default -- match on
    either, since which one shows is real persisted state, not a bug."""
    import api_key_store
    key_present = bool(api_key_store.get_api_key())

    at_openings = _page_apptest("openings_view")
    at_openings.run(timeout=60)
    opening_buttons = [b for b in at_openings.button if "commentary" in b.label]
    assert opening_buttons, "Opening commentary button not found"
    assert opening_buttons[0].disabled == (not key_present)

    at_matchups = _page_apptest("matchups_view", call_with_dummy_pages=True)
    at_matchups.run(timeout=60)
    opponent_buttons = [b for b in at_matchups.button if "commentary" in b.label]
    assert opponent_buttons, "Opponent commentary button not found"
    assert opponent_buttons[0].disabled == (not key_present)


def test_narrative_is_deterministic_for_the_same_game():
    """Same game_id -> byte-identical narrative text across two separate
    calls (not just "looks similar") -- this is the property the whole
    seeded-RNG design exists to guarantee.

    Tested directly through narrative.py/data.py rather than by driving
    the Game Explorer UI: AppTest (Streamlit's headless test harness) has
    no way to simulate a dataframe row-click selection event (a real
    framework limitation, confirmed by inspecting the dataframe element's
    available attributes -- no select_row()/click() method exists), so
    a UI-level version of this test isn't possible since the row-click
    redesign. This is arguably the better test anyway: it exercises the
    actual determinism guarantee without depending on UI simulation."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from _common import resolve_db_path, get_sqlite_connection
    import data
    import narrative

    db_path = resolve_db_path()
    conn = get_sqlite_connection(db_path)
    # Any real game_id works for a determinism check -- fetch one from
    # whatever database is actually configured rather than hardcoding a
    # specific original-project game_id, which wouldn't exist in a fresh
    # install's database.
    any_game_id = conn.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
    header, moves = data.get_game_detail(conn, any_game_id)
    narrative_1 = narrative.generate_narrative(header, moves)
    narrative_2 = narrative.generate_narrative(header, moves)
    assert narrative_1 == narrative_2


def test_overview_css_is_well_formed_style_block():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from overview_view import OVERVIEW_CSS
    assert OVERVIEW_CSS.strip().startswith("<style>")
    assert OVERVIEW_CSS.strip().endswith("</style>")
    assert ".cw-ov-rail" in OVERVIEW_CSS
    assert "theme.POSITIVE" not in OVERVIEW_CSS  # must be interpolated, not literal


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
