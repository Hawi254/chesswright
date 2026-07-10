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
        "training_queue_view",  # render(drill_export_page=None, prep_page=None, analysis_jobs_page=None) defaults
        "points_view",  # render(self_page=None, detail_page=None) defaults
        "srs_drill_view",  # renders upsell when pro_gate inactive, full tabs when active
        "evolution_view",
        "batch_impact_view",  # render(self_page=None, detail_page=None) defaults
        "analysis_jobs_view",  # render(batch_impact_page=None) default
        "ask_view",  # free-tier body when pro_gate inactive, delegates to AI Coach when active
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
class TestAskViewFreeTierUnchanged:
    """Dedicated coverage for the Pro gate added to ask_view.py. Confirms
    the free-tier body (preset buttons, ask_history session state) still
    renders exactly as before, and that the chesswright_pro import path is
    never attempted, when pro_gate.is_pro_active() is False -- the actual
    state in this dev/test environment (no license key active), verified
    directly rather than assumed."""

    def test_pro_gate_inactive_in_this_environment(self):
        import pro_gate
        assert pro_gate.is_pro_active() is False

    def test_free_tier_renders_with_preset_buttons_and_upsell(self, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)

        at = _page_apptest("ask_view")
        at.run(timeout=60)
        assert not at.exception, f"ask_view raised: {at.exception}"

        # Free-tier preset-question buttons still render (unchanged body).
        preset_labels = {b.label for b in at.button}
        assert "Blunder timing" in preset_labels
        assert "Ask" in preset_labels

        # Honest upsell blurb present, no Pro-import error surfaced.
        assert any("AI Coach" in i.value for i in at.info)
        assert not at.error


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
        # sqlite_conn, not duck -- get_game_detail was switched to the
        # native connection in the 2026-07-04 point-lookup pass.
        from _common import resolve_db_path, get_sqlite_connection
        import data
        import narrative

        conn = get_sqlite_connection(resolve_db_path())
        row = conn.execute("SELECT id FROM games LIMIT 1").fetchone()
        if row is None:
            pytest.skip("No games in database")
        any_game_id = row[0]
        header, moves = data.get_game_detail(conn, any_game_id)
        n1 = narrative.generate_narrative(header, moves)
        n2 = narrative.generate_narrative(header, moves)
        assert n1 == n2, "Narrative is not deterministic for the same game"


@pytest.mark.ui
class TestAnalysisJobsBackfillSection:
    """Dedicated coverage for the eval-reuse cache backfill section added to
    analysis_jobs_view.py. Unlike every other test in this file, this one
    actually WRITES (the backfill button click writes batch_eval_cache
    rows) -- so, per this project's rule against tests touching the real
    chess.db, it runs against an isolated tmp_path scratch DB pre-seeded
    with backfill-eligible historical moves, with
    analysis_jobs_view.resolve_db_path monkeypatched to point at it (same
    module-attribute-patch approach as tests/unit/test_duckdb_extension_
    loading.py's monkeypatch.setattr(_common, ...) pattern, adapted here
    since AppTest's LocalScriptRunner runs the generated script in-process,
    so the patched module attribute is visible to it)."""

    def _seed_pending_db(self, db_path):
        import sqlite3
        import chess
        from migrate import migrate

        migrate(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO analysis_runs (id, started_at, depth, multipv) VALUES (1, 't0', 8, 1)")
        conn.execute("""
            INSERT INTO games (id, white, black, num_plies, last_analyzed_ply, analysis_status, queue_order)
            VALUES ('g1', 'W', 'B', 1, 1, 'done', 0)
        """)
        fen_before = chess.Board().fen()
        conn.execute("""
            INSERT INTO moves (id, game_id, ply, move_number, color, san, fen_before, engine_version,
                                analysis_run_id, eval_source)
            VALUES (1, 'g1', 1, 1, 'white', 'e4', ?, 'Stockfish 16', 1, 'engine')
        """, (fen_before,))
        conn.execute("""
            INSERT INTO move_lines (move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact)
            VALUES (1, 1, 35, NULL, 'e4', '["e4"]', 1)
        """)
        conn.commit()
        conn.close()

    def test_backfill_button_appears_and_backfill_click_writes_cache(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "pending.db")
        self._seed_pending_db(db_path)

        import analysis_jobs_view
        monkeypatch.setattr(analysis_jobs_view, "resolve_db_path", lambda: db_path)

        at = _page_apptest("analysis_jobs_view")
        at.run(timeout=60)
        assert not at.exception, f"analysis_jobs_view raised: {at.exception}"

        backfill_buttons = [b for b in at.button if "Backfill eval-reuse cache now" in b.label]
        assert backfill_buttons, "Backfill button not shown despite a pending eligible position"

        backfill_buttons[0].click().run(timeout=60)
        assert not at.exception, f"analysis_jobs_view raised on backfill click: {at.exception}"

        successes = [s.value for s in at.success]
        assert any("Backfilled" in s for s in successes), f"No backfill success message: {successes}"

        import sqlite3
        conn = sqlite3.connect(db_path)
        cache_count = conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0]
        conn.close()
        assert cache_count > 0, "Backfill click did not actually write batch_eval_cache rows"
