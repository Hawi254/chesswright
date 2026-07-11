"""Integration tests for achievements.py -- the Achievements Service.
See docs/superpowers/specs/2026-07-11-achievements-service-design.md.

Uses the real migrated schema (migrated_db fixture) throughout --
achievements.py is sqlite_conn-only (no DuckDB), so no _duck_from_conn
dance is needed here, unlike tests/integration/test_data_layer.py.
"""
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
