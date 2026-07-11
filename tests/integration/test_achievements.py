"""Integration tests for achievements.py -- the Achievements Service.
See docs/superpowers/specs/2026-07-11-achievements-service-design.md.

Uses the real migrated schema (migrated_db fixture) throughout --
achievements.py is sqlite_conn-only (no DuckDB), so no _duck_from_conn
dance is needed here, unlike tests/integration/test_data_layer.py.
"""
import pathlib
import sqlite3

import pytest


@pytest.mark.integration
class TestAchievementsMigration:
    def test_achievements_unlocked_table_exists(self, migrated_db):
        cols = {row[1] for row in migrated_db.execute(
            "PRAGMA table_info(achievements_unlocked)").fetchall()}
        assert cols == {"achievement_id", "unlocked_at", "source_game_id"}


@pytest.mark.integration
class TestSeedCatalogOneTimeEvents:
    def _insert_game(self, conn, game_id, outcome_for_player, rating_diff=0,
                      utc_date="2025.01.01", utc_time="12:00:00", analysis_status="pending"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, rating_diff, "
            "utc_date, utc_time, analysis_status) VALUES (?, 'W', 'B', ?, ?, ?, ?, ?)",
            (game_id, outcome_for_player, rating_diff, utc_date, utc_time, analysis_status))
        conn.commit()

    def test_first_win_unlocks_on_first_win_game(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss")
        self._insert_game(migrated_db, "g2", "win", utc_date="2025.01.02")
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "first_win" in unlocked
        row = migrated_db.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='first_win'"
        ).fetchone()
        assert row[0] == "g2"

    def test_first_win_does_not_unlock_without_a_win(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss")
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "first_win" not in unlocked

    def test_giant_killer_unlocks_on_qualifying_upset(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "win", rating_diff=-350)
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "giant_killer" in unlocked

    def test_giant_killer_requires_a_win_not_just_the_rating_gap(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss", rating_diff=-350)
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "giant_killer" not in unlocked

    def test_comeback_kid_unlocks_on_recovered_win(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "win")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before) VALUES ('g1', 1, 1, 'w', 'e4', 1, 0.05)")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis")
        assert "comeback_kid" in unlocked

    def test_comeback_kid_requires_a_win_or_draw_outcome(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before) VALUES ('g1', 1, 1, 'w', 'e4', 1, 0.05)")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis")
        assert "comeback_kid" not in unlocked


@pytest.fixture
def achievements_config(tmp_path):
    """Small thresholds so seed-catalog tests are deterministic and don't
    depend on the real config.yaml's actual values (which are tuned for
    the real ~32k-game dev DB, not a handful of hand-seeded test rows)."""
    cfg_text = (
        "achievements:\n"
        "  win_streak_length: 3\n"
        "  consistency_streak_days: 3\n"
        "  drill_streak_days: 3\n"
        "  marathon_min_plies: 40\n"
        "  opening_explorer_min_distinct: 2\n"
        "  session_warrior_min_games: 3\n"
        "  century_club_min_analyzed: 2\n"
        "analytics:\n"
        "  session_gap_minutes: 60\n"
    )
    cfg_path = tmp_path / "achievements_config.yaml"
    cfg_path.write_text(cfg_text)
    return str(cfg_path)


@pytest.mark.integration
class TestSeedCatalogThresholds:
    def _insert_game(self, conn, game_id, outcome_for_player="win", num_plies=10,
                      opening_family=None, analysis_status="pending",
                      utc_date="2025.01.01", utc_time="12:00:00"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, num_plies, "
            "opening_family, analysis_status, utc_date, utc_time) "
            "VALUES (?, 'W', 'B', ?, ?, ?, ?, ?, ?)",
            (game_id, outcome_for_player, num_plies, opening_family, analysis_status,
             utc_date, utc_time))
        conn.commit()

    def test_century_club_unlocks_at_threshold(self, migrated_db, achievements_config):
        import achievements
        for i in range(2):
            self._insert_game(migrated_db, f"g{i}", analysis_status="done")
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "century_club" in unlocked

    def test_century_club_not_unlocked_below_threshold(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", analysis_status="done")
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "century_club" not in unlocked

    def test_marathon_game_unlocks_on_long_game(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", num_plies=45)
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "marathon_game" in unlocked

    def test_opening_explorer_unlocks_on_enough_variety(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", opening_family="Italian Game")
        self._insert_game(migrated_db, "g1", opening_family="Sicilian Defense")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "opening_explorer" in unlocked

    def test_blunder_free_game_unlocks_on_clean_analyzed_game(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", analysis_status="done")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "classification) VALUES ('g0', 1, 1, 'w', 'e4', 1, 'good')")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "blunder_free_game" in unlocked

    def test_blunder_free_game_not_unlocked_with_a_blunder(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", analysis_status="done")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "classification) VALUES ('g0', 1, 1, 'w', 'e4', 1, 'blunder')")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "blunder_free_game" not in unlocked


@pytest.mark.integration
class TestSeedCatalogStreaks:
    def _insert_game(self, conn, game_id, outcome_for_player, utc_date, utc_time="12:00:00"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
            "VALUES (?, 'W', 'B', ?, ?, ?)",
            (game_id, outcome_for_player, utc_date, utc_time))
        conn.commit()

    def test_win_streak_unlocks_at_threshold_and_records_last_game(
            self, migrated_db, achievements_config):
        import achievements
        for i in range(3):
            self._insert_game(migrated_db, f"g{i}", "win", f"2025.01.0{i+1}")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "win_streak_10" in unlocked
        row = migrated_db.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='win_streak_10'"
        ).fetchone()
        assert row[0] == "g2"

    def test_win_streak_not_unlocked_when_streak_is_broken(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", "win", "2025.01.01")
        self._insert_game(migrated_db, "g1", "loss", "2025.01.02")
        self._insert_game(migrated_db, "g2", "win", "2025.01.03")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "win_streak_10" not in unlocked

    def test_consistency_streak_unlocks_on_consecutive_days(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", "win", "2025.01.01")
        self._insert_game(migrated_db, "g1", "win", "2025.01.02")
        self._insert_game(migrated_db, "g2", "win", "2025.01.03")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "consistency_streak" in unlocked

    def test_consistency_streak_not_unlocked_with_a_gap_day(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", "win", "2025.01.01")
        self._insert_game(migrated_db, "g1", "win", "2025.01.03")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "consistency_streak" not in unlocked

    def test_drill_streak_unlocks_on_consecutive_review_days(self, migrated_db, achievements_config):
        import achievements
        migrated_db.execute(
            "INSERT INTO srs_cards (fen, source, best_move_san, next_due, added_at) "
            "VALUES ('fen1', 'motif', 'e4', '2025-02-01', '2025-01-01')")
        card_id = migrated_db.execute("SELECT id FROM srs_cards").fetchone()[0]
        for day in ("2025-01-01", "2025-01-02", "2025-01-03"):
            migrated_db.execute(
                "INSERT INTO srs_reviews (card_id, reviewed_at, rating, interval_days_after) "
                "VALUES (?, ?, 2, 1)", (card_id, f"{day}T10:00:00"))
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "drill_streak" in unlocked


@pytest.mark.integration
class TestSeedCatalogBespoke:
    def _insert_game_with_move(self, conn, game_id, outcome, min_wp, utc_date="2025.01.01"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
            "VALUES (?, 'W', 'B', ?, ?, '12:00:00')", (game_id, outcome, utc_date))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before) VALUES (?, 1, 1, 'w', 'e4', 1, ?)", (game_id, min_wp))
        conn.commit()

    def test_swindle_artist_unlocks_on_win_from_a_lost_position(
            self, migrated_db, achievements_config):
        import achievements
        self._insert_game_with_move(migrated_db, "g0", "win", 0.10)
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "swindle_artist" in unlocked

    def test_swindle_artist_does_not_unlock_on_a_draw(self, migrated_db, achievements_config):
        import achievements
        self._insert_game_with_move(migrated_db, "g0", "draw", 0.10)
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "swindle_artist" not in unlocked

    def test_comeback_kid_still_works_after_the_shared_helper_refactor(
            self, migrated_db, achievements_config):
        import achievements
        self._insert_game_with_move(migrated_db, "g0", "draw", 0.05)
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "comeback_kid" in unlocked

    def test_session_warrior_unlocks_on_a_large_session(self, migrated_db, achievements_config):
        import achievements
        for i, minute in enumerate((0, 5, 10)):
            migrated_db.execute(
                "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
                "VALUES (?, 'W', 'B', 'win', '2025.01.01', ?)",
                (f"g{i}", f"10:{minute:02d}:00"))
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "session_warrior" in unlocked
        row = migrated_db.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='session_warrior'"
        ).fetchone()
        assert row[0] == "g2"

    def test_session_warrior_not_unlocked_below_threshold(self, migrated_db, achievements_config):
        import achievements
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
            "VALUES ('g0', 'W', 'B', 'win', '2025.01.01', '10:00:00')")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "session_warrior" not in unlocked


FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures"


def _find_real_stockfish():
    from worker import find_engine_path
    return find_engine_path(None)


REAL_STOCKFISH = _find_real_stockfish()


@pytest.mark.integration
@pytest.mark.skipif(REAL_STOCKFISH is None, reason="no Stockfish binary on this machine")
def test_worker_run_calls_achievements_evaluate_after_analyzing(tmp_path, monkeypatch):
    import migrate as migrate_mod
    import ingest
    import worker
    import achievements

    db_path = str(tmp_path / "test.db")
    migrate_mod.migrate(db_path)
    ingest.ingest(pgn_path=str(FIXTURES_DIR / "synthetic_games.pgn"), db_path=db_path,
                  player_name="TestPlayerWhite")

    calls = []
    monkeypatch.setattr(achievements, "evaluate",
                         lambda conn, trigger, **kw: calls.append(trigger))
    monkeypatch.setattr(worker.joblock, "LOCK_PATH", tmp_path / "test.db.lock")
    monkeypatch.setattr(worker.joblock, "_lock_fd", None)

    worker.run(db_path, depth=6, multipv=1, threads=1, hash_mb=16, pv_max_len=10,
               engine_path=REAL_STOCKFISH, max_games=3, max_duration_s=None,
               consecutive_failure_limit=3, commit_every_n_moves=1)
    worker.joblock.release()

    assert calls == ["analysis"]


@pytest.mark.integration
def test_sync_run_calls_achievements_evaluate_after_new_games(tmp_path, monkeypatch):
    import shutil
    import migrate as migrate_mod
    import sync
    import achievements

    db_path = str(tmp_path / "test.db")
    migrate_mod.migrate(db_path)

    def _fake_fetch(player_name, since_ms, timeout_seconds, max_games=None):
        copy_path = str(tmp_path / "fetched.pgn")
        shutil.copy(str(FIXTURES_DIR / "synthetic_games.pgn"), copy_path)
        return copy_path

    monkeypatch.setattr(sync, "fetch_new_games_pgn", _fake_fetch)
    calls = []
    monkeypatch.setattr(achievements, "evaluate",
                         lambda conn, trigger, **kw: calls.append(trigger))

    sync.run(db_path, "TestPlayerWhite", queue_strategy="chronological",
             berserk_max_fraction=1.0, variant_policy="skip", timeout_seconds=5)

    assert calls == ["sync"]


@pytest.mark.integration
def test_backfill_achievements_is_idempotent(migrated_db_path):
    import backfill_achievements

    conn = sqlite3.connect(migrated_db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
        "VALUES ('g1', 'W', 'B', 'win', '2025.01.01', '12:00:00')")
    conn.commit()
    conn.close()

    backfill_achievements.backfill(migrated_db_path)
    conn = sqlite3.connect(migrated_db_path)
    first_count = conn.execute("SELECT COUNT(*) FROM achievements_unlocked").fetchone()[0]
    conn.close()
    assert first_count >= 1  # at least first_win

    backfill_achievements.backfill(migrated_db_path)
    conn = sqlite3.connect(migrated_db_path)
    second_count = conn.execute("SELECT COUNT(*) FROM achievements_unlocked").fetchone()[0]
    conn.close()
    assert second_count == first_count
