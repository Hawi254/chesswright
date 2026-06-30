"""
UI tests using Streamlit's AppTest harness.

These supersede the standalone dashboard/test_app.py for the pytest run.
The existing test_app.py is left in place for direct invocation
(`python3 dashboard/test_app.py`), but all logic is duplicated here in
pytest form so the CI suite gets coverage.

IMPORTANT: AppTest requires the real database configured in config.yaml to
exist and be non-empty enough for most queries to work.  Tests that can run
against an empty/minimal DB are separated from those that require real data.
"""
import pathlib
import sys
import tempfile
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

APP_PATH = str(DASHBOARD_DIR / "app.py")


def _page_apptest(module_name, call_with_dummy_pages=False):
    """Same helper as dashboard/test_app.py — generates a tiny script and
    runs it via AppTest.from_file so module-level imports are resolved."""
    from streamlit.testing.v1 import AppTest
    call = "render(None, None)" if call_with_dummy_pages else "render()"
    script = (
        f"import sys\nsys.path.insert(0, {str(DASHBOARD_DIR)!r})\n"
        f"import {module_name}\nfrom {module_name} import render\n{call}\n"
    )
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    tmp.write(script)
    tmp.close()
    return AppTest.from_file(tmp.name)


@pytest.mark.ui
class TestAppLaunches:
    def test_app_runs_without_exception(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=60)
        assert not at.exception, f"App raised: {at.exception}"


@pytest.mark.ui
class TestAllCareerPagesRender:
    """Each page's render() is exercised directly (AppTest can only render
    app.py's default page when called via from_file on the full app)."""

    @pytest.mark.parametrize("module_name", [
        "patterns_view",
        "openings_view",
        "game_endings_view",
        "insights_view",
    ])
    def test_no_arg_page_renders(self, module_name):
        at = _page_apptest(module_name)
        at.run(timeout=60)
        assert not at.exception, f"{module_name} raised: {at.exception}"

    @pytest.mark.parametrize("module_name", [
        "overview_view",
        "matchups_view",
        "tactical_highlights_view",
    ])
    def test_two_arg_page_renders(self, module_name):
        at = _page_apptest(module_name, call_with_dummy_pages=True)
        at.run(timeout=60)
        assert not at.exception, f"{module_name} raised: {at.exception}"


@pytest.mark.ui
class TestOpeningsFilter:
    def test_min_games_slider_changes_row_count(self):
        at = _page_apptest("openings_view")
        at.run(timeout=60)
        sliders = [s for s in at.slider if s.label == "Minimum games"]
        if not sliders:
            pytest.skip("Minimum games slider not present — may need more data")
        slider = sliders[0]

        slider.set_value(1).run(timeout=60)
        n_low = len(at.dataframe[0].value) if at.dataframe else 0

        slider.set_value(50).run(timeout=60)
        n_high = len(at.dataframe[0].value) if at.dataframe else 0

        assert n_low >= n_high, (
            f"Raising min_games should never increase row count "
            f"(got {n_low} at 1, {n_high} at 50)")


@pytest.mark.ui
class TestHeadlineMetrics:
    def test_total_games_metric_matches_db(self):
        from streamlit.testing.v1 import AppTest
        sys.path.insert(0, str(DASHBOARD_DIR))
        from _common import resolve_db_path, get_sqlite_connection

        conn = get_sqlite_connection(resolve_db_path())
        real_total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

        if real_total == 0:
            pytest.skip("No games in database — Total games metric not rendered")

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=60)
        metric_values = {m.label: m.value for m in at.metric}
        assert metric_values.get("Total games") == f"{real_total:,}"


@pytest.mark.ui
class TestApiKeyButtonState:
    def test_commentary_buttons_disabled_without_key(self):
        """Commentary buttons must be disabled when no API key is configured."""
        sys.path.insert(0, str(DASHBOARD_DIR))
        import api_key_store
        key_present = bool(api_key_store.get_api_key())

        at_openings = _page_apptest("openings_view")
        at_openings.run(timeout=60)
        opening_buttons = [b for b in at_openings.button if "commentary" in b.label.lower()]
        if not opening_buttons:
            pytest.skip("Opening commentary button not present — may need more data")
        assert opening_buttons[0].disabled == (not key_present)


@pytest.mark.ui
class TestNarrativeDeterminism:
    def test_same_game_gives_identical_narrative(self):
        """Seeded RNG: two calls for the same game must produce byte-identical text."""
        from _common import resolve_db_path, get_duckdb_connection
        import data
        import narrative

        conn = get_duckdb_connection(resolve_db_path())
        row = conn.execute("SELECT id FROM db.games LIMIT 1").fetchone()
        if row is None:
            pytest.skip("No games in database")
        any_game_id = row[0]
        header, moves = data.get_game_detail(conn, any_game_id)
        n1 = narrative.generate_narrative(header, moves)
        n2 = narrative.generate_narrative(header, moves)
        assert n1 == n2, "Narrative is not deterministic for the same game"
