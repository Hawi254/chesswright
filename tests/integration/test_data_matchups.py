"""Integration tests for dashboard/data/matchups.py -- split from
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
class TestMatchupsData:
    def test_get_giant_killing_counts_on_empty_db(self, migrated_db):
        from data.matchups import get_giant_killing_counts
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_giant_killing_counts(duck)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_comeback_collapse_counts_on_empty_db(self, migrated_db):
        from data.matchups import get_comeback_collapse_counts
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_comeback_collapse_counts(duck)
            assert result is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_nemesis_opponents_all_lichess_gate(self, migrated_db):
        """all_lichess must be 1 only when EVERY game vs an opponent is a
        lichess game -- it gates the Opponent Prep deep link, which scouts
        lichess usernames only (see get_nemesis_opponents' comment)."""
        from data.matchups import get_nemesis_opponents
        rows = [
            # ("all_lichess_foe": every game on lichess -> gate open)
            ("g1", "all_lichess_foe", "loss", "https://lichess.org/aaa"),
            ("g2", "all_lichess_foe", "loss", "https://lichess.org/bbb"),
            ("g3", "all_lichess_foe", "win",  "https://lichess.org/ccc"),
            # ("mixed_foe": one chess.com game -> gate closed even though
            #  the other two are lichess)
            ("g4", "mixed_foe", "loss", "https://lichess.org/ddd"),
            ("g5", "mixed_foe", "draw", "https://lichess.org/eee"),
            ("g6", "mixed_foe", "loss", "https://www.chess.com/game/live/123"),
        ]
        for gid, opp, outcome, site in rows:
            migrated_db.execute(
                "INSERT INTO games (id, white, black, opponent_name, "
                "outcome_for_player, site) VALUES (?, 'W', 'B', ?, ?, ?)",
                (gid, opp, outcome, site))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_nemesis_opponents(duck, min_games=3)
            gate = dict(zip(df.opponent_name, df.all_lichess))
            assert gate["all_lichess_foe"] == 1
            assert gate["mixed_foe"] == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_nemesis_opponents_surprise_index(self, migrated_db):
        """expected_score_pct is the average per-game Elo-predicted score
        (logistic, 400-point scale) for rating_diff, NOT the score implied
        by the opponent's average rating_diff -- those differ once
        per-game gaps vary (Jensen's inequality), so this seeds two
        DIFFERENT rating_diff values averaging to the same mean and checks
        against the per-game hand-computed expectation, not a single
        plugged-in average."""
        import math
        from data.matchups import get_nemesis_opponents
        # rating_diff +100 and +300 (avg +200) -- three total games, all
        # losses, to stay above min_games=3.
        rows = [("g1", 100), ("g2", 300), ("g3", 200)]
        for gid, rd in rows:
            migrated_db.execute(
                "INSERT INTO games (id, white, black, opponent_name, "
                "outcome_for_player, rating_diff) VALUES (?, 'W', 'B', 'Foe', 'loss', ?)",
                (gid, rd))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_nemesis_opponents(duck, min_games=3)
            row = df[df.opponent_name == "Foe"].iloc[0]
            expected_frac = sum(1.0 / (1.0 + 10 ** (-rd / 400.0)) for _, rd in rows) / len(rows)
            assert row.score_pct == 0.0
            assert row.expected_score_pct == pytest.approx(100.0 * expected_frac)
            assert row.surprise_pct == pytest.approx(0.0 - 100.0 * expected_frac)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_collapse_causes_on_empty_db(self, migrated_db):
        from data.matchups import get_giant_killing_collapse_causes
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            reason_df, piece_df, mate_df = get_giant_killing_collapse_causes(duck)
            assert reason_df.empty and piece_df.empty and mate_df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_collapse_game(self, conn, game_id, num_plies, moves, rating_diff=300):
        """moves: list of dicts, one per ply, color/is_player_move derived
        the same way TestPointsData._seed_causes_game does (player is
        White). num_plies drives the "near the end" window
        (hallucination_max_moves_to_resign*2 plies, default 6)."""
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "rating_diff, num_plies) VALUES (?, 'W', 'B', 'loss', ?, ?)",
            (game_id, rating_diff, num_plies))
        for mv in moves:
            ply = mv["ply"]
            color = "w" if ply % 2 == 1 else "b"
            is_player_move = mv.get("is_player_move", 1 if color == "w" else 0)
            conn.execute("""
                INSERT INTO moves (game_id, ply, move_number, color, san,
                    is_player_move, classification, cpl, eval_cp, eval_mate,
                    clock_seconds, is_capture, material_delta, to_square, piece)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, ply, (ply + 1) // 2, color, mv.get("san", "e4"),
                  is_player_move, mv.get("classification"), mv.get("cpl"),
                  mv.get("eval_cp"), mv.get("eval_mate"), mv.get("clock_seconds"),
                  mv.get("is_capture", 0), mv.get("material_delta"), mv.get("to_square"),
                  mv.get("piece")))
        conn.commit()

    def test_get_giant_killing_collapse_causes_classifies_reasons(self, migrated_db):
        from data.matchups import get_giant_killing_collapse_causes
        # num_plies=10, window=6 plies -> ply>=4 counts as "near the end".
        self._seed_collapse_game(migrated_db, "gk_hang", 10, [
            {"ply": 7, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5"},
            {"ply": 8, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
        ])
        self._seed_collapse_game(migrated_db, "gk_mate", 10, [
            {"ply": 7, "eval_mate": -4, "san": "Nf3"},
        ])
        self._seed_collapse_game(migrated_db, "gk_timepressure", 10, [
            {"ply": 7, "clock_seconds": 10},
            {"ply": 8, "is_player_move": 0, "clock_seconds": 90},
        ])
        self._seed_collapse_game(migrated_db, "gk_other", 10, [
            {"ply": 3, "eval_cp": 50, "cpl": 10, "classification": "good"},
        ])
        self._seed_collapse_game(migrated_db, "gk_not_analyzed", 10, [
            {"ply": 3, "san": "Nf3"},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            reason_df, piece_df, mate_df = get_giant_killing_collapse_causes(duck)
            reason_lookup = dict(zip(reason_df.reason, reason_df.n))
            assert reason_lookup["hung_piece"] == 1
            assert reason_lookup["faced_mate"] == 1
            assert reason_lookup["time_pressure"] == 1
            assert reason_lookup["other"] == 1
            assert reason_lookup["not_analyzed"] == 1
            assert dict(zip(piece_df.hung_piece, piece_df.n)) == {"Q": 1}
            assert mate_df.iloc[0]["bucket"] == "Mate in 3-5"  # eval_mate=-4
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_collapse_causes_hang_beats_faced_mate(self, migrated_db):
        """Same priority order as get_resignation_loss_causes: hung_piece
        wins over faced_mate when both signals qualify."""
        from data.matchups import get_giant_killing_collapse_causes
        self._seed_collapse_game(migrated_db, "gk_priority", 10, [
            {"ply": 5, "eval_mate": -4, "san": "Nf3"},
            {"ply": 7, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5"},
            {"ply": 8, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            reason_df, _piece_df, _mate_df = get_giant_killing_collapse_causes(duck)
            reason_lookup = dict(zip(reason_df.reason, reason_df.n))
            assert reason_lookup["hung_piece"] == 1
            assert reason_lookup.get("faced_mate", 0) == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_rate_trend_on_empty_db(self, migrated_db):
        from data.matchups import get_giant_killing_rate_trend
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_giant_killing_rate_trend(duck)
            assert df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_rate_trend_zero_fills_and_computes_pct(self, migrated_db):
        from data.matchups import get_giant_killing_rate_trend
        rows = [
            # Q1 2025: one upset win out of one underdog game; one
            # favorite game, no collapse.
            ("g1", 2025, 1, -300, "win"),
            ("g2", 2025, 1, 300, "win"),
            # Q3 2025 (Q2 deliberately skipped -- must zero-fill): one
            # favorite game, one collapse.
            ("g3", 2025, 7, 300, "loss"),
        ]
        for gid, year, month, rd, outcome in rows:
            migrated_db.execute(
                "INSERT INTO games (id, white, black, outcome_for_player, "
                "rating_diff, year, month) VALUES (?, 'W', 'B', ?, ?, ?, ?)",
                (gid, outcome, rd, year, month))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_giant_killing_rate_trend(duck)
            by_label = df.set_index("label")
            assert by_label.loc["2025 Q1", "n_underdog"] == 1
            assert by_label.loc["2025 Q1", "pct_upset"] == pytest.approx(100.0)
            assert by_label.loc["2025 Q1", "n_favorite"] == 1
            assert by_label.loc["2025 Q1", "pct_collapse"] == pytest.approx(0.0)
            assert by_label.loc["2025 Q3", "n_favorite"] == 1
            assert by_label.loc["2025 Q3", "pct_collapse"] == pytest.approx(100.0)
            # zero-filled gap quarter between Q1 and Q3.
            assert "2025 Q2" in by_label.index
            assert by_label.loc["2025 Q2", "n_favorite"] == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_opponent_profile_on_empty_db(self, migrated_db):
        from data.matchups import get_opponent_profile
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            profile = get_opponent_profile(duck, "NoOne")
            assert profile["n_games"] == 0
            assert profile["openings"].empty
            assert profile["position"].empty
            assert profile["castling"].empty
            assert profile["action_side"].empty
            assert profile["clock"].empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_opponent_game(self, conn, game_id, opponent_name, opening_family, outcome,
                            base_seconds, castle_white_sq, castle_black_sq, capture_square,
                            fen_at_checkpoint, cpl, classification, clock_seconds):
        """One game exercising all 5 opponent-profile axes at once: an
        opening_family + outcome/cpl row (openings axis), a ply=24
        (real config.yaml middlegame_ply) fen_before row (position axis),
        one castle move per side (castling axis), one capture (action-side
        axis), and clock_seconds on the same is_player_move cpl row
        (clock axis)."""
        conn.execute(
            "INSERT INTO games (id, white, black, opponent_name, opening_family, "
            "outcome_for_player, base_seconds) VALUES (?, 'W', 'B', ?, ?, ?, ?)",
            (game_id, opponent_name, opening_family, outcome, base_seconds))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_castle, to_square) "
            "VALUES (?, 1, 1, 'w', 'O-O', 1, ?)", (game_id, castle_white_sq))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_castle, to_square) "
            "VALUES (?, 2, 1, 'b', 'O-O', 1, ?)", (game_id, castle_black_sq))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_capture, to_square) "
            "VALUES (?, 3, 2, 'w', 'Nxc6', 1, ?)", (game_id, capture_square))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, fen_before) "
            "VALUES (?, 24, 12, 'w', 'Nf3', ?)", (game_id, fen_at_checkpoint))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "cpl, classification, clock_seconds) VALUES (?, 30, 15, 'w', 'Qd2', 1, ?, ?, ?)",
            (game_id, cpl, classification, clock_seconds))
        conn.commit()

    def test_get_opponent_profile_seeded(self, migrated_db):
        """Two games vs. 'Foe' (different openings, one same-side/kingside-
        heavy win, one opposite-side/queenside-heavy loss) plus a decoy
        game vs. a different opponent using the SAME opening_family/FEN --
        confirms the WHERE opponent_name filter, not just the underlying
        groupby logic (already covered for the whole-DB case by
        TestPositionCharacterData)."""
        from data.matchups import get_opponent_profile
        CLOSED_FEN = "rnbqkbnr/ppp2ppp/4p3/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3"
        OPEN_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
        # g1: same-side castling (kingside/kingside), one kingside capture
        # (e5) -> kingside-heavy, closed position, comfortable clock (0.5),
        # no blunder.
        self._seed_opponent_game(
            migrated_db, "g1", "Foe", "Sicilian Defense", "win", 300,
            "g1", "g8", "e5", CLOSED_FEN, 20, "good", 150)
        # g2: opposite-side castling (queenside/kingside), two queenside
        # captures -> queenside-heavy, open position, critical clock
        # (0.033), blunder.
        self._seed_opponent_game(
            migrated_db, "g2", "Foe", "French Defense", "loss", 300,
            "c1", "g8", "b6", OPEN_FEN, 80, "blunder", 10)
        # g3: decoy, different opponent, same opening/FEN shape as g1 --
        # must be excluded from every 'Foe' axis below.
        self._seed_opponent_game(
            migrated_db, "g3", "Other", "Sicilian Defense", "win", 300,
            "g1", "g8", "e5", CLOSED_FEN, 20, "good", 150)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            profile = get_opponent_profile(duck, "Foe")
            assert profile["n_games"] == 2

            openings = {row.opening_family: (row.n_games, row.win_pct, row.acpl)
                        for row in profile["openings"].itertuples()}
            assert openings["Sicilian Defense"] == (1, 100.0, 20.0)
            assert openings["French Defense"] == (1, 0.0, 80.0)

            position = {row.bucket: (row.n_games, row.win_pct)
                        for row in profile["position"].itertuples()}
            assert position["closed"] == (1, 100.0)
            assert position["open"] == (1, 0.0)

            castling = {row.castling_config: (row.n_games, row.win_pct)
                        for row in profile["castling"].itertuples()}
            assert castling["same-side"] == (1, 100.0)
            assert castling["opposite-side"] == (1, 0.0)

            action_side = {row.action_side: (row.n_games, row.win_pct)
                           for row in profile["action_side"].itertuples()}
            assert action_side["kingside-heavy"] == (1, 100.0)
            assert action_side["queenside-heavy"] == (1, 0.0)

            clock = {row.bucket: (row.n_moves, row.acpl, row.blunder_rate)
                     for row in profile["clock"].itertuples()}
            assert clock["comfortable (30-60%)"] == (1, 20.0, 0.0)
            assert clock["critical (<5%)"] == (1, 80.0, 100.0)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_nemesis_opponents_uses_config_min_sample_size(self, migrated_db, monkeypatch):
        from data import matchups as matchups_module
        monkeypatch.setattr(
            matchups_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 1}})
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "opponent_name, rating_diff) VALUES ('g1', 'W', 'B', 'loss', 'Bob', 0)")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = matchups_module.get_nemesis_opponents(duck)
            assert "Bob" in df.opponent_name.values  # 1 game qualifies at min_sample_size=1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_opponent_swindle_rate(self):
        """Pure pandas, no DB -- covers the WHERE-opponent filter, the
        loss-only filter, and the missed_swindle share, plus the
        None-not-zero convention when there are no losses at all."""
        import pandas as pd
        from data.matchups import get_opponent_swindle_rate
        ledger = pd.DataFrame([
            {"opponent_name": "Foe", "outcome_for_player": "loss", "bucket": "missed_swindle"},
            {"opponent_name": "Foe", "outcome_for_player": "loss", "bucket": "none"},
            {"opponent_name": "Foe", "outcome_for_player": "win", "bucket": "none"},
            {"opponent_name": "Other", "outcome_for_player": "loss", "bucket": "missed_swindle"},
        ])
        result = get_opponent_swindle_rate(ledger, "Foe")
        assert result == {"n_losses": 2, "n_missed_swindle": 1, "swindle_rate_pct": 50.0}

        no_loss_result = get_opponent_swindle_rate(ledger, "NoOne")
        assert no_loss_result == {"n_losses": 0, "n_missed_swindle": 0, "swindle_rate_pct": None}


