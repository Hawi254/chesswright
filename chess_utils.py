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


FILE_LETTERS = "abcdefgh"


def _pawn_files_from_fen(fen: str) -> dict:
    """Parses just the FEN board field into {file_letter: [(rank, color), ...]}
    for pawns only -- deliberately NOT a chess.Board() reconstruction (no
    legality/move-generation needed for pure pawn geometry), which is what
    keeps classify_position_character cheap enough to run over an entire
    game corpus at query time (benchmarked: ~31k games classified in
    ~1.1s) rather than needing a persisted cache table."""
    board_part = fen.split(" ", 1)[0]
    pawn_files = {f: [] for f in FILE_LETTERS}
    for rank_idx, rank_str in enumerate(board_part.split("/")):
        rank_num = 8 - rank_idx  # FEN ranks run 8 (first) down to 1 (last)
        file_idx = 0
        for ch in rank_str:
            if ch.isdigit():
                file_idx += int(ch)
            else:
                if ch in ("P", "p"):
                    pawn_files[FILE_LETTERS[file_idx]].append((rank_num, "w" if ch == "P" else "b"))
                file_idx += 1
    return pawn_files


def _file_locked(pawn_files: dict, f: str) -> bool:
    """True if a White pawn on this file is directly blocked by a Black
    pawn one rank ahead of it (the textbook "locked pawn chain" shape --
    each side's pawn immobile until a capture happens elsewhere)."""
    whites = [r for r, c in pawn_files[f] if c == "w"]
    blacks = [r for r, c in pawn_files[f] if c == "b"]
    return any(br == wr + 1 for wr in whites for br in blacks)


def _files_have_tension(pawn_files: dict, f1: str, f2: str) -> bool:
    """True if a pawn on f1 and a pawn on f2 (adjacent files) sit on
    diagonally-capturable ranks for either color -- unresolved "pawn
    tension" (chess.com's "Pawn Tension" lesson), distinct from a locked
    pair (same file, not adjacent files)."""
    w1 = [r for r, c in pawn_files[f1] if c == "w"]
    b1 = [r for r, c in pawn_files[f1] if c == "b"]
    w2 = [r for r, c in pawn_files[f2] if c == "w"]
    b2 = [r for r, c in pawn_files[f2] if c == "b"]
    return (any(br == wr + 1 for wr in w1 for br in b2) or
            any(br == wr + 1 for wr in w2 for br in b1))


def classify_position_character(fen: str) -> dict:
    """Classifies a position's pawn structure along the axes chess theory
    uses for "what kind of game is this" (chessprogramming.org's Pawn
    Structure/Open File/Half-open File entries; chess.com's open/semi-open/
    closed definitions): central pawns traded off + open files == open;
    a locked central pawn chain == closed; anything else == semi-open.

    bucket: 'open' (neither d- nor e-file has ANY pawn, either color --
      the center is fully liquidated) / 'closed' (the d- or e-file has a
      locked White-vs-Black pawn pair) / 'semi-open' (everything else --
      e.g. one central pawn traded, the other still locked or untouched).
    open_files: count of the 8 files with no pawn of either color --
      a continuous companion signal to the 3-way bucket.
    symmetric: White's and Black's occupied-pawn-file sets are identical
      (ignoring rank) -- a coarse, cheap proxy for "mirrored" structures;
      says nothing about symmetry of pieces or files with rank
      differences.
    central_tension: unresolved diagonal pawn tension (chess.com's "Pawn
      Tension" lesson) on the c/d, d/e, or e/f file pairs -- a nuance
      within 'semi-open' positions, not itself a bucket value.
    white_space / black_space: sum of each side's pawn advancement
      (White: rank number; Black: 9 - rank number) -- a simplified proxy
      for chessprogramming.org's "Space" evaluation term, NOT a
      reconstruction of Stockfish's actual safe-square-count formula.

    This is a single-snapshot simplification (matches the existing
    accepted imprecision of analytics.py's middlegame_ply checkpoint --
    a position can still transition from closed to open later in the
    same game), not a mid-game-tracking classifier."""
    pawn_files = _pawn_files_from_fen(fen)
    open_files = sum(1 for f in FILE_LETTERS if not pawn_files[f])
    center_empty = not pawn_files["d"] and not pawn_files["e"]
    center_locked = _file_locked(pawn_files, "d") or _file_locked(pawn_files, "e")
    if center_empty:
        bucket = "open"
    elif center_locked:
        bucket = "closed"
    else:
        bucket = "semi-open"
    white_files = {f for f in FILE_LETTERS if any(c == "w" for _, c in pawn_files[f])}
    black_files = {f for f in FILE_LETTERS if any(c == "b" for _, c in pawn_files[f])}
    central_tension = (_files_have_tension(pawn_files, "c", "d") or
                        _files_have_tension(pawn_files, "d", "e") or
                        _files_have_tension(pawn_files, "e", "f"))
    white_space = sum(r for f in FILE_LETTERS for r, c in pawn_files[f] if c == "w")
    black_space = sum((9 - r) for f in FILE_LETTERS for r, c in pawn_files[f] if c == "b")
    return {
        "bucket": bucket,
        "open_files": open_files,
        "symmetric": white_files == black_files,
        "central_tension": central_tension,
        "white_space": white_space,
        "black_space": black_space,
    }


def classify_bishop_color_ending(fen: str):
    """Classifies same-color vs. opposite-color bishops from a FEN's board
    field alone -- a square's color is (file_idx + rank_num) % 2 (a1 is
    file 0/rank 1 -> odd -> dark, the standard alternating pattern).
    Deliberately NOT a chess.Board() reconstruction, same reasoning as
    _pawn_files_from_fen: pure square-color geometry needs no legality or
    move-generation machinery.

    Only meaningful when each side has EXACTLY one bishop on the board --
    material_sig carries piece counts but no square-color information at
    all, which is exactly why this needs a real FEN parse instead of a
    signature-string check (roadmap's Material Structure Explorer Tier 2
    gap). Returns None for zero, two, or unequal bishop counts per side --
    the "opposite-color bishops" concept doesn't generalize past 1-vs-1,
    same "no bucket fits" convention as classify_position_character's
    callers use for a game that doesn't reach a checkpoint."""
    board_part = fen.split(" ", 1)[0]
    white_squares = []
    black_squares = []
    for rank_idx, rank_str in enumerate(board_part.split("/")):
        rank_num = 8 - rank_idx
        file_idx = 0
        for ch in rank_str:
            if ch.isdigit():
                file_idx += int(ch)
            else:
                if ch == "B":
                    white_squares.append((file_idx + rank_num) % 2)
                elif ch == "b":
                    black_squares.append((file_idx + rank_num) % 2)
                file_idx += 1
    if len(white_squares) != 1 or len(black_squares) != 1:
        return None
    return "same" if white_squares[0] == black_squares[0] else "opposite"


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
