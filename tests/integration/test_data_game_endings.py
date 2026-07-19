"""Integration tests for dashboard/data/game_endings.py -- split from
test_data_layer.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import os
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _duck_from_conn

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.mark.integration
class TestGameEndingsData:
    def test_get_time_forfeit_loss_breakdown_on_empty_db(self, migrated_db):
        from data.game_endings import get_time_forfeit_loss_breakdown
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            material_df, scramble_df, trend_df = get_time_forfeit_loss_breakdown(duck)
            assert material_df.empty and scramble_df.empty and trend_df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_time_forfeit_game(self, conn, game_id, year, month, day,
                                 mover_color, material_sig, material_delta,
                                 player_color, opponent_clock):
        """mover_color: color ('w'/'b') that made the FINAL recorded move of
        the game -- inserted at the highest ply so get_time_forfeit_loss_
        breakdown's last_move CTE (ORDER BY ply DESC) picks up ITS
        material_sig/material_delta. The opponent's last clock reading, if
        any, is a LOWER-ply row -- it must not sit at the highest ply, or
        it would shadow the material row (whose material_sig would then be
        NULL) in that same CTE."""
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, game_end_type, "
            "player_color, year, month, utc_date) VALUES (?, 'W', 'B', 'loss', "
            "'time_forfeit', ?, ?, ?, ?)",
            (game_id, player_color, year, month, f"{year}.{month:02d}.{day:02d}"))
        player_move_color = "w" if player_color == "white" else "b"
        opponent_move_color = "b" if player_color == "white" else "w"
        if opponent_clock is not None:
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, clock_seconds, "
                "is_player_move) VALUES (?, 1, 1, ?, 'Nf3', ?, 0)",
                (game_id, opponent_move_color, opponent_clock))
        is_player = 1 if mover_color == player_move_color else 0
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, material_sig, "
            "material_delta, is_player_move) VALUES (?, 2, 1, ?, 'e5', ?, ?, ?)",
            (game_id, mover_color, material_sig, material_delta, is_player))
        conn.commit()

    def test_get_time_forfeit_loss_breakdown_classifies_material_and_scramble(self, migrated_db):
        from data.game_endings import get_time_forfeit_loss_breakdown
        # White (the player) made the final recorded move in both games.
        # g1: ahead by a rook (+500), opponent had plenty of time
        # (one-sided). g2: level material, opponent also nearly out
        # (mutual scramble).
        self._seed_time_forfeit_game(
            migrated_db, "g1", 2025, 3, 1, mover_color="w",
            material_sig="R2P7vP7", material_delta=0,
            player_color="white", opponent_clock=90)
        self._seed_time_forfeit_game(
            migrated_db, "g2", 2025, 6, 1, mover_color="w",
            material_sig="P7vP7", material_delta=0,
            player_color="white", opponent_clock=5)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            material_df, scramble_df, trend_df = get_time_forfeit_loss_breakdown(duck)
            material_lookup = dict(zip(material_df.bucket, material_df.n))
            assert material_lookup["ahead by 3+ points"] == 1
            assert material_lookup["roughly level"] == 1
            scramble_lookup = dict(zip(scramble_df.bucket, scramble_df.n))
            assert scramble_lookup["mutual scramble (opponent under 15s)"] == 1
            assert scramble_lookup["opponent comfortable (60s+)"] == 1
            assert trend_df["n_total"].sum() == 2
            # Q1 and Q2 2025 are non-adjacent quarters -- the zero-fill must
            # produce a Q2-only-empty row in between, not skip straight from
            # Q1 to Q2 with nothing.
            assert set(trend_df.label) >= {"2025 Q1", "2025 Q2"}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_time_forfeit_loss_breakdown_black_player_orientation(self, migrated_db):
        """Black being ahead must read as 'ahead' from the player's own
        perspective, not White's -- the exact sign bug this classification
        would produce if player_color were ignored."""
        from data.game_endings import get_time_forfeit_loss_breakdown
        self._seed_time_forfeit_game(
            migrated_db, "g3", 2025, 1, 1, mover_color="b",
            material_sig="P7vR2P7", material_delta=0,
            player_color="black", opponent_clock=90)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            material_df, _scramble_df, _trend_df = get_time_forfeit_loss_breakdown(duck)
            material_lookup = dict(zip(material_df.bucket, material_df.n))
            assert material_lookup["ahead by 3+ points"] == 1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_time_forfeit_loss_breakdown_filters_by_time_control(self, migrated_db):
        from data.game_endings import get_time_forfeit_loss_breakdown
        self._seed_time_forfeit_game(
            migrated_db, "g_bullet", 2025, 3, 1, mover_color="w",
            material_sig="R2P7vP7", material_delta=0,
            player_color="white", opponent_clock=90)
        migrated_db.execute("UPDATE games SET time_control_category = 'bullet' WHERE id = 'g_bullet'")
        self._seed_time_forfeit_game(
            migrated_db, "g_blitz", 2025, 3, 1, mover_color="w",
            material_sig="R2P7vP7", material_delta=0,
            player_color="white", opponent_clock=90)
        migrated_db.execute("UPDATE games SET time_control_category = 'blitz' WHERE id = 'g_blitz'")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            material_df, _scramble_df, _trend_df = get_time_forfeit_loss_breakdown(duck, time_control="bullet")
            material_lookup = dict(zip(material_df.bucket, material_df.n))
            assert material_lookup["ahead by 3+ points"] == 1

            material_df_all, _s, _t = get_time_forfeit_loss_breakdown(duck)
            material_lookup_all = dict(zip(material_df_all.bucket, material_df_all.n))
            assert material_lookup_all["ahead by 3+ points"] == 2
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_resignation_game(self, conn, game_id, year, month, day, time_control_category=None):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, game_end_type, "
            "year, month, utc_date, time_control_category) VALUES (?, 'W', 'B', 'loss', "
            "'resignation', ?, ?, ?, ?)",
            (game_id, year, month, f"{year}.{month:02d}.{day:02d}", time_control_category))
        conn.commit()

    def test_get_resignation_loss_causes_filters_by_time_control(self, migrated_db):
        from data.game_endings import get_resignation_loss_causes
        self._seed_resignation_game(migrated_db, "g_bullet", 2025, 3, 1, time_control_category="bullet")
        self._seed_resignation_game(migrated_db, "g_blitz", 2025, 3, 1, time_control_category="blitz")
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            reason_df, _piece_df, _mate_df = get_resignation_loss_causes(duck, time_control="bullet")
            assert int(reason_df.n.sum()) == 1
            reason_df_all, _p, _m = get_resignation_loss_causes(duck)
            assert int(reason_df_all.n.sum()) == 2
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


