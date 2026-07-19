"""Golden-text test guarding the ask_view.py -> dashboard/data/ask_brief.py
extraction (see docs/superpowers/specs/2026-07-17-ask-page-design.md,
decision 5) -- asserts the streamlit-free build_ask_data_brief() produces
byte-identical output to ask_view.py's pre-extraction _build_data_brief()
for the same fixture DB.
"""
import pathlib
import shutil
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.fixture
def ask_brief_connections(populated_db, migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("TestPlayerWhite", path=str(scratch_config))
    _config.set_database_path(migrated_db_path, path=str(scratch_config))

    import connections
    connections.clear_cache()
    sqlite_conn, duck_conn = connections.open_connections()
    return sqlite_conn, duck_conn


@pytest.mark.unit
def test_build_ask_data_brief_matches_legacy(ask_brief_connections):
    sqlite_conn, duck_conn = ask_brief_connections

    import ask_view
    legacy = ask_view._build_data_brief(duck_conn, sqlite_conn)

    from data.ask_brief import build_ask_data_brief
    extracted = build_ask_data_brief(duck_conn, sqlite_conn)

    assert extracted == legacy
    assert "HEADLINE STATS:" in extracted
