"""
Shared fixtures for the Chesswright test suite.

All DB fixtures use temp files on disk (not :memory:) because migrate() and
ingest() both take file paths.  Fixtures are function-scoped so every test
gets a clean slate.
"""
import pathlib
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

@pytest.fixture
def migrated_db_path(tmp_path):
    """Path to a freshly migrated SQLite DB file."""
    from migrate import migrate
    db_path = str(tmp_path / "test.db")
    migrate(db_path)
    return db_path


@pytest.fixture
def migrated_db(migrated_db_path):
    """sqlite3 connection to a freshly migrated DB (foreign keys ON)."""
    conn = sqlite3.connect(migrated_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def populated_db(migrated_db_path):
    """Migrated DB pre-loaded with 3 synthetic games and sample move rows."""
    import ingest as ingest_mod
    ingest_mod.ingest(
        pgn_path=str(SYNTHETIC_PGN),
        db_path=migrated_db_path,
        player_name="TestPlayerWhite",
    )
    conn = sqlite3.connect(migrated_db_path)
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
