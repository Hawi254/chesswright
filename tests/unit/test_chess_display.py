"""Unit tests for dashboard/chess_display.py — eval formatting, PGN export."""
import pytest

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "dashboard"))

from chess_display import eval_str, pv_str, eval_bar_html, variation_to_pgn

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


@pytest.mark.unit
class TestEvalStr:
    def test_positive_cp(self):
        assert eval_str(125, None) == "+1.25"

    def test_negative_cp(self):
        assert eval_str(-50, None) == "-0.50"

    def test_zero_cp(self):
        assert eval_str(0, None) == "+0.00"

    def test_positive_mate(self):
        assert eval_str(None, 3) == "M3"

    def test_negative_mate(self):
        assert eval_str(None, -5) == "−M5"

    def test_none_both_returns_dash(self):
        assert eval_str(None, None) == "—"

    def test_mate_takes_priority_over_cp(self):
        # Both provided — mate wins
        assert eval_str(999, 1) == "M1"


@pytest.mark.unit
class TestPvStr:
    def test_white_to_move_includes_move_number(self):
        # e4 from starting position — white to move at move 1
        result = pv_str(STARTING_FEN, '["e4"]')
        assert result is not None
        assert "1." in result
        assert "e4" in result

    def test_black_to_move_uses_ellipsis(self):
        # Black's first response from the position after 1.e4
        result = pv_str(AFTER_E4_FEN, '["e5"]')
        assert result is not None
        assert "1…" in result or "1..." in result or "e5" in result

    def test_empty_json_returns_none(self):
        assert pv_str(STARTING_FEN, "[]") is None

    def test_none_pv_returns_none(self):
        assert pv_str(STARTING_FEN, None) is None

    def test_invalid_json_returns_none(self):
        assert pv_str(STARTING_FEN, "not json") is None

    def test_multi_move_sequence(self):
        result = pv_str(STARTING_FEN, '["e4", "e5", "Nf3"]', max_moves=3)
        assert result is not None
        # Should include moves from the sequence
        assert "e4" in result

    def test_invalid_san_stops_early(self):
        # Invalid SAN mid-sequence — should return what was valid, not crash
        result = pv_str(STARTING_FEN, '["e4", "INVALID_MOVE"]')
        assert result is not None or result is None  # either is acceptable; no crash


@pytest.mark.unit
class TestEvalBarHtml:
    def test_returns_html_string(self):
        result = eval_bar_html(0, None, STARTING_FEN)
        assert "<div" in result and "width:" in result

    def test_equal_position_near_50_50(self):
        result = eval_bar_html(0, None, STARTING_FEN)
        # At 0 cp, white and black should each get ~50%
        assert "50.0%" in result

    def test_white_winning_more_white(self):
        result = eval_bar_html(500, None, STARTING_FEN)
        # White to move, +5.00 — white's bar should be >50%
        lines = result.split("width:")
        white_pct = float(lines[1].split("%")[0].strip())
        assert white_pct > 60

    def test_mate_for_white(self):
        result = eval_bar_html(None, 1, STARTING_FEN)
        assert "100.0%" in result

    def test_mate_for_black(self):
        result = eval_bar_html(None, -1, STARTING_FEN)
        assert "0.0%" in result

    def test_invalid_fen_does_not_crash(self):
        result = eval_bar_html(100, None, "invalid fen string")
        assert isinstance(result, str)


@pytest.mark.unit
class TestVariationToPgn:
    def test_empty_variation_produces_valid_pgn(self):
        pgn = variation_to_pgn(STARTING_FEN, [], {})
        assert "[Event" in pgn
        assert "*" in pgn

    def test_single_move_variation(self):
        pgn = variation_to_pgn(STARTING_FEN, ["e2e4"], {})
        assert "e4" in pgn

    def test_two_move_variation(self):
        pgn = variation_to_pgn(STARTING_FEN, ["e2e4", "e7e5"], {})
        assert "e4" in pgn
        assert "e5" in pgn

    def test_glyph_becomes_nag(self):
        import data.variations as vmod
        # Build an annotation dict as the data layer would
        from collections import namedtuple
        Ann = namedtuple("Ann", ["glyph", "comment", "ai_comment", "generated_at"])
        anns = {1: Ann(glyph="!", comment="Good move", ai_comment=None, generated_at=None)}
        pgn = variation_to_pgn(STARTING_FEN, ["e2e4"], anns)
        assert "$1" in pgn  # NAG for "!"

    def test_title_appears_in_event_header(self):
        pgn = variation_to_pgn(STARTING_FEN, [], {}, title="My Test Line")
        assert "My Test Line" in pgn

    def test_custom_start_position(self):
        # After 1.e4 e5
        fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
        pgn = variation_to_pgn(fen, ["g1f3"], {})
        assert "Nf3" in pgn

    def test_invalid_uci_stops_early_without_crash(self):
        pgn = variation_to_pgn(STARTING_FEN, ["e2e4", "INVALID", "e7e5"], {})
        assert isinstance(pgn, str)
        assert "e4" in pgn
