"""Integration tests for snapshots.py -- the historical snapshot store.
See docs/superpowers/specs/2026-07-14-insights-page-redesign-phase2-
snapshot-store-design.md.

Uses the real migrated schema (migrated_db fixture), same convention as
tests/integration/test_achievements.py -- snapshots.py is sqlite_conn-only
(no DuckDB), so no _duck_from_conn dance is needed here.
"""
import pytest


@pytest.mark.integration
class TestMetricSnapshotsMigration:
    def test_metric_snapshots_table_exists(self, migrated_db):
        cols = {row[1] for row in migrated_db.execute(
            "PRAGMA table_info(metric_snapshots)").fetchall()}
        assert cols == {
            "snapshot_date", "total_games", "analyzed_games", "acpl",
            "blunder_rate", "win_pct", "n_analyzed_moves", "implied_rating",
            "rating_confidence",
        }


@pytest.mark.integration
class TestRecordSnapshot:
    def _insert_game(self, conn, game_id, outcome_for_player="win", analysis_status="done"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, analysis_status) "
            "VALUES (?, 'W', 'B', ?, ?)",
            (game_id, outcome_for_player, analysis_status))
        conn.commit()

    def _insert_analyzed_move(self, conn, game_id, ply, cpl, classification="good"):
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "cpl, classification) VALUES (?, ?, ?, 'w', 'e4', 1, ?, ?)",
            (game_id, ply, (ply + 1) // 2, cpl, classification))
        conn.commit()

    def test_zero_games_gives_null_rating_fields(self, migrated_db):
        import snapshots
        snapshots.record_snapshot(migrated_db)

        row = migrated_db.execute(
            "SELECT total_games, analyzed_games, acpl, blunder_rate, win_pct, "
            "n_analyzed_moves, implied_rating, rating_confidence FROM metric_snapshots"
        ).fetchone()
        assert row == (0, 0, None, None, None, 0, None, None)

    def test_snapshot_matches_hand_computed_values(self, migrated_db):
        import snapshots
        self._insert_game(migrated_db, "g1", outcome_for_player="win")
        self._insert_game(migrated_db, "g2", outcome_for_player="loss")
        for i in range(25):
            self._insert_analyzed_move(migrated_db, "g1", i + 1, cpl=20)
        self._insert_analyzed_move(migrated_db, "g2", 1, cpl=400, classification="blunder")

        snapshots.record_snapshot(migrated_db)

        row = migrated_db.execute(
            "SELECT total_games, analyzed_games, acpl, blunder_rate, win_pct, "
            "n_analyzed_moves, implied_rating, rating_confidence FROM metric_snapshots"
        ).fetchone()
        total_games, analyzed_games, acpl, blunder_rate, win_pct, n_moves, implied_rating, rating_confidence = row
        assert total_games == 2
        assert analyzed_games == 2  # both games' analysis_status='done'
        assert n_moves == 26
        assert acpl == pytest.approx((20 * 25 + 400) / 26, rel=1e-6)
        assert blunder_rate == pytest.approx(100.0 / 26, rel=1e-6)
        assert win_pct == 50.0  # 1 win / 2 games with a recorded outcome
        # 26 analyzed moves clears MIN_ANALYZED_MOVES_FOR_SNAPSHOT_RATING (20)
        # at the "low" tier (< 60 for "medium").
        assert rating_confidence == "low"
        assert implied_rating == snapshots._estimate_rating_from_acpl(acpl)

    def test_second_call_same_day_upserts_not_duplicates(self, migrated_db):
        import snapshots
        self._insert_game(migrated_db, "g1")
        snapshots.record_snapshot(migrated_db)

        self._insert_game(migrated_db, "g2")
        snapshots.record_snapshot(migrated_db)

        rows = migrated_db.execute("SELECT total_games FROM metric_snapshots").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 2
