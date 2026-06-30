"""Unit tests for chess_utils.py — pure functions, no DB."""
import chess
import chess.pgn
import io
import pytest

import chess_utils as cu


@pytest.mark.unit
class TestParseClockSeconds:
    def test_basic(self):
        assert cu.parse_clock_seconds("[%clk 0:03:00]") == 180

    def test_hours(self):
        assert cu.parse_clock_seconds("[%clk 1:30:00]") == 5400

    def test_zero(self):
        assert cu.parse_clock_seconds("[%clk 0:00:00]") == 0

    def test_embedded_in_comment(self):
        assert cu.parse_clock_seconds("some text [%clk 0:05:30] more text") == 330

    def test_none_on_missing(self):
        assert cu.parse_clock_seconds("no clock here") is None

    def test_none_on_empty_string(self):
        assert cu.parse_clock_seconds("") is None

    def test_none_on_none_input(self):
        assert cu.parse_clock_seconds(None) is None


@pytest.mark.unit
class TestMaterialSignature:
    def test_starting_position(self):
        board = chess.Board()
        sig = cu.material_signature(board)
        assert sig == "Q1R2B2N2P8vQ1R2B2N2P8"

    def test_after_e4(self):
        board = chess.Board()
        board.push_san("e4")
        sig = cu.material_signature(board)
        assert sig == "Q1R2B2N2P8vQ1R2B2N2P8"

    def test_after_capture(self):
        # Scholar's mate position — white wins black knight's pawns
        board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/2B1P3/8/PPPP1PPP/RNBQK1NR w KQkq - 0 3")
        board.push_san("Qh5")
        board.push_san("Nc6")
        board.push_san("Qxf7")
        sig = cu.material_signature(board)
        # White has captured the f7 pawn — black's pawns drop from 8 to 7
        assert "P7" in sig

    def test_empty_side_shows_no_pieces(self):
        board = chess.Board("8/8/8/8/8/8/8/K7 w - - 0 1")
        sig = cu.material_signature(board)
        assert sig == "v"


@pytest.mark.unit
class TestSignedZobrist:
    def test_starting_position_is_signed_64bit(self):
        board = chess.Board()
        z = cu.signed_zobrist(board)
        assert -(2**63) <= z < 2**63

    def test_two_different_positions_differ(self):
        b1 = chess.Board()
        b2 = chess.Board()
        b2.push_san("e4")
        assert cu.signed_zobrist(b1) != cu.signed_zobrist(b2)

    def test_same_position_same_hash(self):
        b1 = chess.Board()
        b2 = chess.Board()
        assert cu.signed_zobrist(b1) == cu.signed_zobrist(b2)


@pytest.mark.unit
class TestNonPawnPieceCount:
    def test_start_position(self):
        assert cu.non_pawn_piece_count("Q1R2B2N2P8vQ1R2B2N2P8") == 14

    def test_king_only_not_counted(self):
        # Kings are not tracked in the material_signature (they never disappear)
        assert cu.non_pawn_piece_count("P8vP8") == 0

    def test_after_trades(self):
        sig = "R2P7vR2P7"
        assert cu.non_pawn_piece_count(sig) == 4


@pytest.mark.unit
class TestMaterialDeltaForMove:
    def test_quiet_move_is_zero(self):
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        assert cu.material_delta_for_move(board, move) == 0

    def test_capture_pawn(self):
        # After 1.e4 e5, white captures e5
        board = chess.Board()
        board.push_san("e4")
        board.push_san("e5")
        move = chess.Move.from_uci("e4e5")
        assert cu.material_delta_for_move(board, move) == 100

    def test_capture_knight(self):
        # Position where white can capture Nc6
        board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        move = chess.Move.from_uci("c4f7")
        # f7 is a pawn
        assert cu.material_delta_for_move(board, move) == 100

    def test_promotion_delta(self):
        # White pawn on e7 promotes to queen
        board = chess.Board("8/4P3/8/8/8/8/8/k6K w - - 0 1")
        move = chess.Move.from_uci("e7e8q")
        # Gains 900 (queen) - 100 (pawn) = 800
        assert cu.material_delta_for_move(board, move) == 800

    def test_castling_is_zero(self):
        board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        move = chess.Move.from_uci("e1g1")
        assert cu.material_delta_for_move(board, move) == 0

    def test_en_passant_captures_pawn(self):
        # En passant position: black pawn on d5, white pawn on e5, black played d7d5
        board = chess.Board("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3")
        move = chess.Move.from_uci("e5d6")
        assert cu.material_delta_for_move(board, move) == 100
