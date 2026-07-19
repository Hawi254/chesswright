"""
Shared fixtures for the Chesswright test suite.

All DB fixtures use temp files on disk (not :memory:) because migrate() and
ingest() both take file paths. migrate() and ingest() each run exactly once
per test session, against a session-scoped template file; the per-test
fixtures below copy that template so every test still gets its own
isolated, mutable DB.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
SYNTHETIC_PGN = FIXTURES_DIR / "synthetic_games.pgn"


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _migrated_template_db(tmp_path_factory):
    """Runs migrate() exactly once per test session."""
    from migrate import migrate
    template_path = tmp_path_factory.mktemp("template") / "template.db"
    migrate(str(template_path))
    # 0001_init.sql sets journal_mode=WAL; migrate() never closes its own
    # connection, so committed data can still be sitting in template.db-wal
    # rather than the main file. shutil.copy() below only copies the main
    # file, so checkpoint-and-truncate the WAL first or copies silently
    # lose everything but the schema_migrations table.
    conn = sqlite3.connect(template_path)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return template_path


@pytest.fixture(scope="session")
def _populated_template_db(_migrated_template_db, tmp_path_factory):
    """Migrated template + the existing synthetic-game ingest, built once
    per session."""
    import ingest as ingest_mod

    template_path = tmp_path_factory.mktemp("populated") / "template.db"
    shutil.copy(_migrated_template_db, template_path)
    ingest_mod.ingest(
        pgn_path=str(SYNTHETIC_PGN),
        db_path=str(template_path),
        player_name="TestPlayerWhite",
    )
    conn = sqlite3.connect(template_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Add synthetic mock eval data for one game so annotation tests have data
    game_ids = [r[0] for r in conn.execute("SELECT id FROM games").fetchall()]
    for gid in game_ids[:1]:
        plies = [r[0] for r in conn.execute(
            "SELECT ply FROM moves WHERE game_id=? ORDER BY ply", (gid,)).fetchall()]
        for i, ply in enumerate(plies):
            conn.execute(
                "UPDATE moves SET eval_cp=?, eval_mate=NULL WHERE game_id=? AND ply=?",
                (10 * (i % 10 - 5), gid, ply))
        conn.execute(
            "UPDATE games SET analysis_status='done' WHERE id=?", (gid,))
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return template_path


@pytest.fixture
def migrated_db_path(_migrated_template_db, tmp_path):
    """Path to a freshly-copied migrated SQLite DB file — same contract as
    before, but backed by a copy instead of a fresh migrate() run."""
    db_path = tmp_path / "test.db"
    shutil.copy(_migrated_template_db, db_path)
    return str(db_path)


@pytest.fixture
def migrated_db(migrated_db_path):
    """sqlite3 connection to a freshly migrated DB (foreign keys ON)."""
    conn = sqlite3.connect(migrated_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def populated_db(_populated_template_db, tmp_path):
    """Migrated DB pre-loaded with 3 synthetic games and sample move rows —
    same contract as before, but backed by a copy of a session-built
    template instead of running ingest() fresh every test."""
    db_path = tmp_path / "test.db"
    shutil.copy(_populated_template_db, db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def config_yaml(tmp_path):
    """A minimal config.yaml written to a temp directory for mutation tests."""
    cfg_text = (
        'player:\n'
        '  name: "CHANGE_ME"\n'
        'database:\n'
        '  path: chess.db\n'
        'engine:\n'
        '  path: null\n'
        '  depth: 20\n'
        '  multipv: 3\n'
        '  threads: 4\n'
        '  hash_mb: 256\n'
        '  pv_max_len: 15\n'
        '  reuse_evals: true\n'
        'interactive_engine:\n'
        '  threads: 1\n'
        '  hash_mb: 32\n'
        '  time_sec: 0.5\n'
        '  depth: 20\n'
        '  store_threshold: 20\n'
        '  use_lichess_cloud_eval: true\n'
        'analytics:\n'
        '  min_sample_size: 5\n'
        '  utc_offset_hours: 0\n'
        'worker:\n'
        '  consecutive_failure_limit: 3\n'
        '  commit_every_n_moves: 1\n'
        'ingestion:\n'
        '  variant_policy: skip\n'
        '  queue_strategy: interleaved_by_year\n'
        '  berserk_max_clock_fraction: 0.75\n'
        '  backlog_quota: 0.5\n'
        '  backlog_quota_window: 20\n'
        'sync:\n'
        '  request_timeout_seconds: 30\n'
        'sync_chesscom:\n'
        '  request_timeout_seconds: 30\n'
    )
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(cfg_text)
    return cfg_path


# ---------------------------------------------------------------------------
# Patterns API test helpers (shared by 2+ of the split test_api_patterns_*.py
# files — see docs/superpowers/plans/2026-07-17-test-suite-reorg-and-speedup-plan.md)
# ---------------------------------------------------------------------------

def _insert_game(db_path, game_id, base_seconds=180, time_control_category="blitz"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, base_seconds, time_control_category) "
        "VALUES (?, 'W', 'B', ?, ?)",
        [game_id, base_seconds, time_control_category])
    conn.commit()
    conn.close()


def _insert_move(db_path, game_id, ply, move_number=1, color="w", san="Nf3",
                  is_player_move=1, cpl=None, classification=None,
                  clock_seconds=None, time_spent_seconds=None, legal_reply_count=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, "
        "classification, clock_seconds, time_spent_seconds, legal_reply_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [game_id, ply, move_number, color, san, is_player_move, cpl,
         classification, clock_seconds, time_spent_seconds, legal_reply_count])
    conn.commit()
    conn.close()


@pytest.fixture
def api_client(migrated_db_path, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    monkeypatch.setattr(_config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import connections
    connections.clear_cache()

    import api.main as api_main
    api_main.reset_caches()
    return TestClient(api_main.app)


# ---------------------------------------------------------------------------
# More patterns API test helpers, discovered missing from the plan's Step 1
# grep (it only anchored on _insert_game/_insert_move/api_client) when the
# split's first live run hit NameError across test_api_patterns_pieces.py,
# test_api_patterns_game_context.py, and test_api_patterns_summary.py --
# these 4 are each called from 2+ of the split test_api_patterns_*.py files,
# so per this plan's shared-helper rule they move here too.
# ---------------------------------------------------------------------------

def _insert_full_game(db_path, game_id, player_color="white", outcome_for_player=None,
                       num_plies=40, base_seconds=180):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, player_color, outcome_for_player, "
        "num_plies, base_seconds) VALUES (?, 'W', 'B', ?, ?, ?, ?)",
        [game_id, player_color, outcome_for_player, num_plies, base_seconds])
    conn.commit()
    conn.close()


def _insert_full_move(db_path, game_id, ply, move_number=1, color="w", san="Nf3",
                       is_player_move=1, cpl=None, classification=None, piece=None,
                       to_square=None, is_castle=0, sharpness=None, material_sig=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, "
        "classification, piece, to_square, is_castle, sharpness, material_sig) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [game_id, ply, move_number, color, san, is_player_move, cpl, classification,
         piece, to_square, is_castle, sharpness, material_sig])
    conn.commit()
    conn.close()


def _seed_rating_bucket_game(db_path, game_id, rating_diff, outcome, cpl=None, opening_family=None):
    """One game + one moves row -- get_favorite_underdog_performance's
    query INNER JOINs moves, so a game with zero moves rows would never
    appear in its result at all, even though cpl is optional (win_df
    doesn't need it). Mirrors test_event_type_performance.py's _seed_game
    shape."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, rating_diff, outcome_for_player, opening_family) "
        "VALUES (?, 'W', 'B', ?, ?, ?)", (game_id, rating_diff, outcome, opening_family))
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl) "
        "VALUES (?, 1, 1, 'w', 'e4', 1, ?)", (game_id, cpl))
    conn.commit()
    conn.close()


def _seed_session_game(db_path, game_id, utc_date, utc_time, outcome, n_moves=1, cpl=None):
    """One game + n_moves analyzed player moves, all sharing the same cpl
    -- n_moves lets the session-tendency-card test clear MIN_BUCKET_MOVES
    (20) per bucket without a second helper. utc_date/utc_time drive
    analytics.compute_session_context's chronological walk (format
    matches test_data_layer.py's existing session/rating-snapshot seeds:
    'YYYY.MM.DD' / 'HH:MM:SS')."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
        "VALUES (?, 'W', 'B', ?, ?, ?)", (game_id, outcome, utc_date, utc_time))
    for i in range(n_moves):
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl) "
            "VALUES (?, ?, ?, 'w', 'e4', 1, ?)", (game_id, i + 1, i + 1, cpl))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Data-layer test helper (shared by 10 of the split test_data_*.py files --
# see docs/superpowers/plans/2026-07-17-test-suite-reorg-and-speedup-plan.md)
# ---------------------------------------------------------------------------

def _duck_from_conn(sqlite_conn):
    """
    Copy the in-memory SQLite connection to a temp file and attach it to
    a fresh DuckDB connection.  Returns (duck_conn, disk_conn, tmp_path)
    -- callers must close all three and delete the temp file.
    """
    import duckdb
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    disk = sqlite3.connect(tmp.name)
    for line in sqlite_conn.iterdump():
        try:
            disk.execute(line)
        except Exception:
            pass
    disk.commit()
    duck = duckdb.connect(":memory:")
    duck.execute(f"ATTACH '{tmp.name}' AS db (TYPE SQLITE, READ_ONLY TRUE)")
    return duck, disk, tmp.name
