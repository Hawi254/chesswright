"""Shared position-identity helpers used by worker.py and backfill_positions.py."""
import re

import chess
import chess.polyglot

PIECE_ORDER = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
PIECE_LETTER = {chess.QUEEN: "Q", chess.ROOK: "R", chess.BISHOP: "B",
                chess.KNIGHT: "N", chess.PAWN: "P"}

NON_PAWN_PIECE_RE = re.compile(r"([QRBN])(\d+)")
CLK_RE = re.compile(r"\[%clk\s+(\d+):(\d{2}):(\d{2})\]")


def parse_clock_seconds(comment: str):
    """Moved here from ingest.py (single source of truth) so
    detect_berserk below can reuse it without a backward dependency on
    ingest.py."""
    m = CLK_RE.search(comment or "")
    if not m:
        return None
    h, mm, s = map(int, m.groups())
    return h * 3600 + mm * 60 + s


def detect_berserk(game, base_seconds, max_fraction):
    """Lichess arenas let a player "berserk" at game start: halves their
    starting clock, cancels their increment for the rest of that game.
    No PGN tag exists for this (confirmed: grepped a real export, only
    hits were usernames containing "berserk") -- derived instead from
    each color's FIRST %clk reading vs base_seconds. Empirically
    validated against 7,026 real clock readings: a perfectly clean
    bimodal split, exactly 1.0 or exactly 0.5, zero values in between --
    no "tolerance for move-1 thinking time" is actually needed, but
    max_fraction is still a config knob (default 0.75, dead center of
    the gap) rather than a hardcoded 0.5/1.0 boundary.

    Cheap pre-pass: comment/ply-parity only, no board replay -- this
    must run BEFORE the caller's own move-walking loop, since that loop's
    ply-1 time_spent calculation depends on already knowing the correct
    starting-clock baseline (the one place a sequencing bug could creep
    in silently here).

    Returns (white_berserk, black_berserk), each True/False/None --
    None specifically means "no clock data for that color," not
    "confirmed not berserk." Returns (None, None) if base_seconds is missing."""
    if base_seconds is None or base_seconds <= 0:
        return None, None
    threshold = base_seconds * max_fraction
    first_clock = {"w": None, "b": None}
    ply = 0
    for node in game.mainline():
        ply += 1
        color = "w" if ply % 2 == 1 else "b"
        if first_clock[color] is None:
            clk = parse_clock_seconds(node.comment)
            if clk is not None:
                first_clock[color] = clk
        if first_clock["w"] is not None and first_clock["b"] is not None:
            break
    white_berserk = None if first_clock["w"] is None else first_clock["w"] <= threshold
    black_berserk = None if first_clock["b"] is None else first_clock["b"] <= threshold
    return white_berserk, black_berserk


def non_pawn_piece_count(material_sig: str) -> int:
    """Total queen/rook/bishop/knight count, both sides combined, parsed
    directly from a material_sig string (e.g. "Q1R2B2N2P7vQ1R2B2N2P7" -> 14).
    Used to detect "reached an endgame" without a new stored column."""
    return sum(int(n) for _, n in NON_PAWN_PIECE_RE.findall(material_sig))


def material_signature(board: chess.Board) -> str:
    def side(color):
        parts = []
        for pt in PIECE_ORDER:
            n = len(board.pieces(pt, color))
            if n:
                parts.append(f"{PIECE_LETTER[pt]}{n}")
        return "".join(parts)
    return f"{side(chess.WHITE)}v{side(chess.BLACK)}"


def signed_zobrist(board: chess.Board) -> int:
    """SQLite INTEGER is signed 64-bit; zobrist_hash is unsigned 64-bit, so wrap it."""
    z = chess.polyglot.zobrist_hash(board)
    return z - 2**64 if z >= 2**63 else z


# cp-like x100 units, consistent scale with eval_cp/cpl.
POINT_VALUE = {
    chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
    chess.ROOK: 500, chess.QUEEN: 900,
}

ALL_PIECE_RE = re.compile(r"([QRBNP])(\d+)")
_SIG_POINT_VALUE = {letter: POINT_VALUE[pt] for pt, letter in PIECE_LETTER.items()}


def material_balance_cp(material_sig: str) -> int:
    """White-minus-black material balance in POINT_VALUE's cp-like x100
    units, parsed from a material_sig string (e.g. "Q1R2P7vR2P6" -> 1000).
    Kings are never in the signature, so they never enter the balance."""
    white_sig, black_sig = material_sig.split("v")
    def side_points(side):
        return sum(_SIG_POINT_VALUE[p] * int(n) for p, n in ALL_PIECE_RE.findall(side))
    return side_points(white_sig) - side_points(black_sig)


def material_delta_for_move(board: chess.Board, move: chess.Move) -> int:
    """Material the MOVER gains by playing this move (captures/promotions),
    evaluated pre-push. Always >= 0 -- a player can never lose material on
    their own move, only the opponent's reply captures something back, so
    this never represents "did the mover sacrifice anything" by itself."""
    if board.is_castling(move):
        return 0
    delta = 0
    if board.is_en_passant(move):
        # to_square is empty pre-push for e.p. -- the captured pawn sits
        # elsewhere, so a naive piece_at(to_square) lookup would miss it.
        delta += POINT_VALUE[chess.PAWN]
    elif board.is_capture(move):
        captured = board.piece_at(move.to_square)
        delta += POINT_VALUE[captured.piece_type]
    if move.promotion is not None:
        delta += POINT_VALUE[move.promotion] - POINT_VALUE[chess.PAWN]
    return delta
