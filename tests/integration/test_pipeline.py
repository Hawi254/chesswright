"""
Integration tests for the ingest → annotate pipeline against a synthetic PGN.

worker.py (Stockfish) is NOT invoked — we write mock eval data directly into
the DB to test the annotation pass in isolation.
"""
import pathlib
import sqlite3
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

import migrate as migrate_mod


def _make_migrated_db_file(tmp_path, name="test.db"):
    db_path = str(tmp_path / name)
    migrate_mod.migrate(db_path)
    return db_path
    return db_path


@pytest.mark.integration
class TestIngestPipeline:
    def test_ingest_synthetic_games(self, tmp_path):
        import ingest
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        assert pgn_path.exists(), "Synthetic PGN fixture not found"
        result = ingest.ingest(
            pgn_path=str(pgn_path),
            db_path=db_path,
            player_name="TestPlayerWhite",
        )
        n_ingested = result[0]
        assert n_ingested >= 1, "Expected at least 1 game ingested"

    def test_player_color_assigned_correctly(self, tmp_path):
        import ingest
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")  # returns tuple, result not needed here
        conn = sqlite3.connect(db_path)
        white_rows = conn.execute(
            "SELECT player_color FROM games WHERE white='TestPlayerWhite'"
        ).fetchall()
        for (color,) in white_rows:
            assert color == "white"
        black_rows = conn.execute(
            "SELECT player_color FROM games WHERE black='TestPlayerWhite'"
        ).fetchall()
        for (color,) in black_rows:
            assert color == "black"
        conn.close()

    def test_moves_stored_for_each_game(self, tmp_path):
        import ingest
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")
        conn = sqlite3.connect(db_path)
        game_ids = [r[0] for r in conn.execute("SELECT id FROM games").fetchall()]
        for gid in game_ids:
            n = conn.execute(
                "SELECT COUNT(*) FROM moves WHERE game_id=?", (gid,)
            ).fetchone()[0]
            assert n > 0, f"Game {gid} has no moves"
        conn.close()

    def test_legal_reply_count_only_set_for_zero_time_moves(self, tmp_path):
        """legal_reply_count (migrations/0032) is populated exactly for the
        instant-move (time_spent_seconds=0) population and NULL everywhere
        else -- ply 1 of synthetic_games.pgn's first game is a natural
        zero-time move (both colors' first %clk reading equals the base
        clock, so last_clock - clock_seconds + increment == 0)."""
        import chess
        import ingest
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")
        conn = sqlite3.connect(db_path)

        zero_time_rows = conn.execute(
            "SELECT fen_before, legal_reply_count FROM moves WHERE time_spent_seconds=0"
        ).fetchall()
        assert len(zero_time_rows) > 0, "Fixture expected to contain at least one zero-time move"
        for fen_before, legal_reply_count in zero_time_rows:
            assert legal_reply_count is not None
            assert legal_reply_count == chess.Board(fen_before).legal_moves.count()

        nonzero_count = conn.execute("""
            SELECT COUNT(*) FROM moves
            WHERE time_spent_seconds IS NOT NULL AND time_spent_seconds != 0
              AND legal_reply_count IS NOT NULL
        """).fetchone()[0]
        assert nonzero_count == 0
        conn.close()

    def test_time_control_category_parsed(self, tmp_path):
        import ingest
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")
        conn = sqlite3.connect(db_path)
        cats = {r[0] for r in conn.execute(
            "SELECT DISTINCT time_control_category FROM games").fetchall()}
        assert "blitz" in cats or "rapid" in cats
        conn.close()

    def test_reopening_db_and_reingest_does_not_duplicate(self, tmp_path):
        """Reingest of the same PGN must not double-insert games (UNIQUE on game id)."""
        import ingest
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        r1 = ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                           player_name="TestPlayerWhite")
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")
        conn = sqlite3.connect(db_path)
        total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        conn.close()
        assert total == r1[0], "Reingest should not duplicate games"


@pytest.mark.integration
class TestLegalReplyCountBackfill:
    def test_backfill_fills_nulled_out_zero_time_rows(self, tmp_path):
        """Simulates data ingested before migrations/0032 existed: NULL out
        legal_reply_count on the zero-time rows ingest.py just populated,
        then confirm backfill_legal_reply_count.py restores the exact same
        values from fen_before alone."""
        import chess
        import ingest
        import backfill_legal_reply_count as backfill_mod
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")

        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE moves SET legal_reply_count=NULL WHERE time_spent_seconds=0")
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM moves WHERE time_spent_seconds=0 AND legal_reply_count IS NULL"
        ).fetchone()[0] > 0

        backfill_mod.backfill(db_path)

        rows = conn.execute(
            "SELECT fen_before, legal_reply_count FROM moves WHERE time_spent_seconds=0"
        ).fetchall()
        assert len(rows) > 0
        for fen_before, legal_reply_count in rows:
            assert legal_reply_count == chess.Board(fen_before).legal_moves.count()
        conn.close()

    def test_backfill_is_idempotent(self, tmp_path):
        import ingest
        import backfill_legal_reply_count as backfill_mod
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE moves SET legal_reply_count=NULL WHERE time_spent_seconds=0")
        conn.commit()

        backfill_mod.backfill(db_path)
        first_pass = conn.execute(
            "SELECT id, legal_reply_count FROM moves WHERE time_spent_seconds=0 ORDER BY id"
        ).fetchall()
        backfill_mod.backfill(db_path)  # second run should be a no-op (nothing left NULL)
        second_pass = conn.execute(
            "SELECT id, legal_reply_count FROM moves WHERE time_spent_seconds=0 ORDER BY id"
        ).fetchall()
        assert first_pass == second_pass
        conn.close()


@pytest.mark.integration
class TestAnnotationPass:
    def test_annotation_runs_without_error(self, tmp_path):
        """Run annotate.run() over mock-eval data — no engine needed."""
        import ingest
        import annotate
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")
        conn = sqlite3.connect(db_path)
        game_ids = [r[0] for r in conn.execute(
            "SELECT id FROM games WHERE analysis_status='pending'").fetchall()]

        # Write synthetic eval_cp values so annotation has data to work with
        for gid in game_ids:
            plies = conn.execute(
                "SELECT ply FROM moves WHERE game_id=? ORDER BY ply", (gid,)
            ).fetchall()
            for i, (ply,) in enumerate(plies):
                conn.execute(
                    "UPDATE moves SET eval_cp=?, eval_mate=NULL WHERE game_id=? AND ply=?",
                    (10 * (i % 10 - 5), gid, ply)
                )
            conn.execute(
                "UPDATE games SET analysis_status='done' WHERE id=?", (gid,)
            )
        conn.commit()

        # annotate.run() uses the real file-based DB path
        annotate.run(
            db_path=db_path,
            mate_cap=1500,
            thresholds={"excellent": 0.02, "good": 0.05, "inaccuracy": 0.10,
                        "mistake": 0.20, "blunder": 0.30},
            brilliant_threshold=None,
            puzzle_cfg={},
            streak_cfg={},
            game_id=None,
        )
        conn.close()

    def test_win_prob_in_range_after_annotation(self, tmp_path):
        """After annotation, all win_prob values must be in [0.0, 1.0]."""
        import ingest
        import annotate
        db_path = _make_migrated_db_file(tmp_path)
        pgn_path = FIXTURES / "synthetic_games.pgn"
        ingest.ingest(pgn_path=str(pgn_path), db_path=db_path,
                      player_name="TestPlayerWhite")
        conn = sqlite3.connect(db_path)
        game_ids = [r[0] for r in conn.execute("SELECT id FROM games").fetchall()]
        for gid in game_ids:
            plies = conn.execute(
                "SELECT ply FROM moves WHERE game_id=? ORDER BY ply", (gid,)).fetchall()
            for i, (ply,) in enumerate(plies):
                conn.execute(
                    "UPDATE moves SET eval_cp=?, eval_mate=NULL WHERE game_id=? AND ply=?",
                    (50, gid, ply))
            conn.execute("UPDATE games SET analysis_status='done' WHERE id=?", (gid,))
        conn.commit()
        annotate.run(
            db_path=db_path, mate_cap=1500,
            thresholds={"excellent": 0.02, "good": 0.05, "inaccuracy": 0.10,
                        "mistake": 0.20, "blunder": 0.30},
            brilliant_threshold=None, puzzle_cfg={}, streak_cfg={}, game_id=None)
        rows = conn.execute(
            "SELECT ply, win_prob_before, win_prob_after FROM moves "
            "WHERE win_prob_before IS NOT NULL"
        ).fetchall()
        for ply, wpb, wpa in rows:
            assert 0.0 <= wpb <= 1.0
            if wpa is not None:
                assert 0.0 <= wpa <= 1.0
        conn.close()
