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
