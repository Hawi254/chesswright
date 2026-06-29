"""Tactical motif classifier using python-chess pattern detection.

classify_motif(fen, best_move_san) -> str | None

Called from annotate.py Pass 4 for mistake/blunder moves where both
fen_before and best_move_san are available. Returns the dominant
tactical idea behind the move the player should have found, or None if
no motif is recognised.

Motifs, checked in priority order (first match wins):
  back_rank_mate  -- best move delivers checkmate on the opponent's back rank
  fork            -- best move attacks 2+ high-value opponent pieces at once
  pin             -- best move creates a new pin on an opponent piece
  discovery       -- best move reveals a new attack from a piece behind the mover
  skewer          -- a line piece attacks a high-value piece with a lower-value
                     piece behind it along the same ray
  hanging         -- best move captures an undefended or under-defended piece

MOTIF_LABELS maps the raw key to a human-readable display string for the UI.
"""
import chess

MOTIF_LABELS = {
    "back_rank_mate": "Back-rank mate",
    "fork":           "Fork",
    "pin":            "Pin",
    "discovery":      "Discovery",
    "skewer":         "Skewer",
    "hanging":        "Hanging piece",
}

_CHECKS = None  # populated on first call to classify_motif


def classify_motif(fen: str, best_move_san: str) -> str | None:
    """Return the dominant tactical motif of best_move_san from fen, or None."""
    global _CHECKS
    if _CHECKS is None:
        _CHECKS = [_back_rank_mate, _fork, _pin, _discovery, _skewer, _hanging]
    try:
        board = chess.Board(fen)
        move = board.parse_san(best_move_san)
    except Exception:
        return None
    for check in _CHECKS:
        if check(board, move):
            return check.__name__.lstrip("_")
    return None


def _back_rank_mate(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    result = False
    if board.is_checkmate():
        king_sq = board.king(board.turn)
        back_rank = chess.BB_RANK_1 if board.turn == chess.WHITE else chess.BB_RANK_8
        result = bool(chess.BB_SQUARES[king_sq] & back_rank)
    board.pop()
    return result


def _fork(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    sq = move.to_square
    piece = board.piece_at(sq)
    if piece is None:
        board.pop()
        return False
    opponent = not piece.color
    n_valuable = sum(
        1 for s in board.attacks(sq)
        if (p := board.piece_at(s)) and p.color == opponent
        and p.piece_type >= chess.KNIGHT
    )
    board.pop()
    return n_valuable >= 2


def _pin(board: chess.Board, move: chess.Move) -> bool:
    opponent = not board.turn
    pins_before = {
        sq for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.color == opponent
        and board.is_pinned(opponent, sq)
    }
    board.push(move)
    opponent_after = board.turn
    pins_after = {
        sq for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.color == opponent_after
        and board.is_pinned(opponent_after, sq)
    }
    board.pop()
    return bool(pins_after - pins_before)


def _discovery(board: chess.Board, move: chess.Move) -> bool:
    player = board.turn
    opponent = not player
    targets = [
        sq for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.color == opponent
        and p.piece_type in (chess.QUEEN, chess.ROOK, chess.KING)
    ]
    if not targets:
        return False
    before = {sq: set(chess.SquareSet(board.attackers(player, sq))) for sq in targets}
    board.push(move)
    player_after = not board.turn
    found = any(
        set(chess.SquareSet(board.attackers(player_after, sq))) - before[sq] - {move.to_square}
        for sq in targets
    )
    board.pop()
    return found


def _squares_beyond(sq_from: int, sq_through: int):
    """Yield squares on the ray from sq_from, past sq_through, in ray order."""
    f_from, r_from = chess.square_file(sq_from), chess.square_rank(sq_from)
    f_thr, r_thr = chess.square_file(sq_through), chess.square_rank(sq_through)
    df, dr = f_thr - f_from, r_thr - r_from
    step_f = 0 if df == 0 else (1 if df > 0 else -1)
    step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
    f, r = f_thr + step_f, r_thr + step_r
    while 0 <= f <= 7 and 0 <= r <= 7:
        yield chess.square(f, r)
        f += step_f
        r += step_r


def _skewer(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    player = not board.turn
    opponent = board.turn
    found = False
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != player:
            continue
        if piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        for target_sq in chess.SquareSet(board.attacks(sq)):
            target = board.piece_at(target_sq)
            if not target or target.color != opponent or target.piece_type < chess.ROOK:
                continue
            for behind_sq in _squares_beyond(sq, target_sq):
                behind = board.piece_at(behind_sq)
                if behind:
                    if behind.color == opponent:
                        found = True
                    break
            if found:
                break
        if found:
            break
    board.pop()
    return found


def _hanging(board: chess.Board, move: chess.Move) -> bool:
    if not board.is_capture(move):
        return False
    captured_sq = move.to_square
    captured = board.piece_at(captured_sq)
    if captured is None:
        return False
    moving = board.piece_at(move.from_square)
    if moving is None:
        return False
    opponent = not board.turn
    if not board.attackers(opponent, captured_sq):
        return True
    return captured.piece_type > moving.piece_type
