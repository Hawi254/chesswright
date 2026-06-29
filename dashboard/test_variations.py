"""Tests for data/variations.py -- run from chess_app/dashboard/ with .venv/bin/python3."""
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import data.variations as v

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE variations (
            id TEXT PRIMARY KEY, game_id TEXT NOT NULL, branch_ply INTEGER NOT NULL,
            branch_fen TEXT NOT NULL, moves_json TEXT NOT NULL DEFAULT '[]',
            title TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE variation_annotations (
            id TEXT PRIMARY KEY, variation_id TEXT NOT NULL, move_index INTEGER NOT NULL,
            glyph TEXT, comment TEXT, ai_comment TEXT, ai_model TEXT, generated_at TEXT,
            UNIQUE (variation_id, move_index),
            FOREIGN KEY (variation_id) REFERENCES variations(id) ON DELETE CASCADE
        );
    """)
    return conn


def test_compute_variation_fen():
    fen = v.compute_variation_fen(STARTING_FEN, ["e2e4"], 1)
    assert "4P3" in fen, f"Expected e4 pawn in fen, got: {fen}"
    fen0 = v.compute_variation_fen(STARTING_FEN, ["e2e4"], 0)
    assert fen0 == STARTING_FEN, "step=0 should return branch_fen unchanged"
    print("PASS test_compute_variation_fen")


def test_compute_variation_fen_invalid_uci():
    """Invalid UCI in the middle of a sequence returns current board state, not crash."""
    result = v.compute_variation_fen(STARTING_FEN, ["e2e4", "INVALID", "e7e5"], 3)
    # Should return the FEN after e4 (the last good move before INVALID), not crash.
    assert "4P3" in result, f"Expected pawn on e4 after recovering from invalid UCI: {result}"
    print("PASS test_compute_variation_fen_invalid_uci")


def test_save_and_list_variations():
    conn = _make_db()
    vid = v.save_variation(conn, "game1", 2, STARTING_FEN, ["e2e4", "e7e5"])
    assert isinstance(vid, str) and len(vid) == 36, f"Bad UUID: {vid}"
    rows = v.list_variations(conn, "game1")
    assert len(rows) == 1, f"Expected 1 variation, got {len(rows)}"
    assert rows[0].game_id == "game1"
    assert rows[0].moves == ["e2e4", "e7e5"]
    assert rows[0].branch_ply == 2
    # Other game returns empty
    assert v.list_variations(conn, "game2") == []
    print("PASS test_save_and_list_variations")


def test_update_variation_moves():
    conn = _make_db()
    vid = v.save_variation(conn, "game1", 1, STARTING_FEN, ["e2e4"])
    v.update_variation_moves(conn, vid, ["e2e4", "e7e5", "g1f3"])
    rows = v.list_variations(conn, "game1")
    assert rows[0].moves == ["e2e4", "e7e5", "g1f3"], f"Moves not updated: {rows[0].moves}"
    print("PASS test_update_variation_moves")


def test_delete_variation():
    conn = _make_db()
    vid = v.save_variation(conn, "game1", 1, STARTING_FEN, ["e2e4"])
    v.delete_variation(conn, vid)
    assert v.list_variations(conn, "game1") == [], "Variation not deleted"
    print("PASS test_delete_variation")


def test_upsert_annotation_insert():
    conn = _make_db()
    vid = v.save_variation(conn, "game1", 1, STARTING_FEN, ["e2e4"])
    v.upsert_annotation(conn, vid, 1, glyph="!", comment="Good move")
    anns = v.get_variation_annotations(conn, vid)
    assert 1 in anns, "Annotation at step 1 missing"
    assert anns[1].glyph == "!", f"Wrong glyph: {anns[1].glyph}"
    assert anns[1].comment == "Good move"
    assert anns[1].ai_comment is None
    print("PASS test_upsert_annotation_insert")


def test_upsert_annotation_update():
    conn = _make_db()
    vid = v.save_variation(conn, "game1", 1, STARTING_FEN, ["e2e4"])
    v.upsert_annotation(conn, vid, 1, comment="First comment")
    v.upsert_annotation(conn, vid, 1, ai_comment="Claude says: central control.")
    anns = v.get_variation_annotations(conn, vid)
    assert anns[1].comment == "First comment", "comment was overwritten"
    assert anns[1].ai_comment == "Claude says: central control."
    assert anns[1].generated_at is not None
    print("PASS test_upsert_annotation_update")


def test_cascade_delete():
    conn = _make_db()
    vid = v.save_variation(conn, "game1", 1, STARTING_FEN, ["e2e4"])
    v.upsert_annotation(conn, vid, 1, comment="Test")
    anns_before = v.get_variation_annotations(conn, vid)
    assert len(anns_before) == 1
    v.delete_variation(conn, vid)
    # Annotations should be cascade-deleted
    anns_after = v.get_variation_annotations(conn, vid)
    assert len(anns_after) == 0, "Annotations not cascade-deleted"
    print("PASS test_cascade_delete")


def test_multi_step_annotations():
    conn = _make_db()
    vid = v.save_variation(conn, "game1", 1, STARTING_FEN, ["e2e4", "e7e5", "g1f3"])
    v.upsert_annotation(conn, vid, 0, comment="Branch point")
    v.upsert_annotation(conn, vid, 1, glyph="!", comment="Good")
    v.upsert_annotation(conn, vid, 2, glyph="?")
    anns = v.get_variation_annotations(conn, vid)
    assert len(anns) == 3
    assert anns[0].comment == "Branch point"
    assert anns[1].glyph == "!"
    assert anns[2].glyph == "?"
    print("PASS test_multi_step_annotations")


if __name__ == "__main__":
    test_compute_variation_fen()
    test_compute_variation_fen_invalid_uci()
    test_save_and_list_variations()
    test_update_variation_moves()
    test_delete_variation()
    test_upsert_annotation_insert()
    test_upsert_annotation_update()
    test_cascade_delete()
    test_multi_step_annotations()
    print("\nAll tests passed.")
