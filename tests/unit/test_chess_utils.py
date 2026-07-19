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
class TestMaterialBalanceCp:
    def test_start_position_is_level(self):
        assert cu.material_balance_cp("Q1R2B2N2P8vQ1R2B2N2P8") == 0

    def test_white_up_a_rook_and_pawn(self):
        # White: Q+2R+7P, Black: 2R+6P -> +900 (queen) +100 (pawn) = +1000
        assert cu.material_balance_cp("Q1R2P7vR2P6") == 1000

    def test_black_ahead_is_negative(self):
        assert cu.material_balance_cp("P8vN1P8") == -300

    def test_bare_kings(self):
        # Kings never appear in the signature, so both sides can be empty.
        assert cu.material_balance_cp("v") == 0

    def test_multi_digit_counts(self):
        # 10 pawns of promotion-feedstock shape still parses (two digits).
        assert cu.material_balance_cp("P10vP8") == 200


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


@pytest.mark.unit
class TestClassifyPositionCharacter:
    def test_starting_position_is_semi_open_and_symmetric(self):
        # Untouched center (neither empty nor locked) falls into the
        # 'semi-open' catch-all by design -- never actually reached in
        # production (only queried at middlegame_ply, 12 full moves in),
        # but the defined behavior for an untouched center is worth
        # pinning down explicitly.
        r = cu.classify_position_character(chess.Board().fen())
        assert r["bucket"] == "semi-open"
        assert r["symmetric"] is True
        assert r["open_files"] == 0
        assert r["central_tension"] is False

    def test_bare_kings_is_open(self):
        r = cu.classify_position_character("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        assert r["bucket"] == "open"
        assert r["open_files"] == 8
        assert r["white_space"] == 0
        assert r["black_space"] == 0

    def test_locked_french_advance_center_is_closed(self):
        # 1.e4 e6 2.d4 d5 3.e5 -- White d4/e5 vs Black d5/e6, both files
        # locked (each side's pawn directly blocked one rank ahead).
        r = cu.classify_position_character(
            "rnbqkbnr/ppp2ppp/4p3/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3")
        assert r["bucket"] == "closed"

    def test_asymmetric_missing_black_d_pawn(self):
        r = cu.classify_position_character(
            "rnbqkbnr/ppp1pppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        assert r["symmetric"] is False

    def test_central_tension_diagonal_unresolved(self):
        # White pawn d4, Black pawn e5 -- diagonally capturable, neither
        # file has a same-file locked pair.
        r = cu.classify_position_character("4k3/8/8/4p3/3P4/8/8/4K3 w - - 0 1")
        assert r["bucket"] == "semi-open"
        assert r["central_tension"] is True
        assert r["white_space"] == 4
        assert r["black_space"] == 4

    def test_no_tension_when_files_not_adjacent(self):
        # White pawn on a4, Black pawn on e5 -- not adjacent files, so no
        # tension despite both being "central-ish" in rank.
        r = cu.classify_position_character("4k3/8/8/4p3/P7/8/8/4K3 w - - 0 1")
        assert r["central_tension"] is False


@pytest.mark.unit
class TestClassifyBishopColorEnding:
    def test_same_color_bishops(self):
        # White bishop c1 (file 2, rank 1, sum=3, odd) and Black bishop f8
        # (file 5, rank 8, sum=13, odd) -- same parity, same square color.
        r = cu.classify_bishop_color_ending("4kb2/8/8/8/8/8/8/2B1K3 w - - 0 1")
        assert r == "same"

    def test_opposite_color_bishops(self):
        # White bishop c1 (odd) and Black bishop c8 (file 2, rank 8, sum=10,
        # even) -- same file, but ranks 7 apart flips the square color.
        r = cu.classify_bishop_color_ending("2bk4/8/8/8/8/8/8/2B1K3 w - - 0 1")
        assert r == "opposite"

    def test_no_bishops_returns_none(self):
        assert cu.classify_bishop_color_ending("4k3/8/8/8/8/8/8/4K3 w - - 0 1") is None

    def test_unequal_bishop_counts_returns_none(self):
        # White has two bishops (c1, f1), Black has one (f8) -- the
        # same/opposite-color concept doesn't generalize past 1-vs-1.
        r = cu.classify_bishop_color_ending("4kb2/8/8/8/8/8/8/2B1KB2 w - - 0 1")
        assert r is None
