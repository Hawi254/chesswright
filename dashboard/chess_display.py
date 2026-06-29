"""Shared position display helpers used by openings_view and game_detail_view."""
import json

import chess


def eval_str(eval_cp, eval_mate) -> str:
    """Format a Stockfish eval as a sign-prefixed string (+1.25, -0.50, M3, -M5)."""
    if eval_mate is not None:
        return f"M{eval_mate}" if eval_mate > 0 else f"−M{abs(eval_mate)}"
    if eval_cp is not None:
        return f"+{eval_cp / 100:.2f}" if eval_cp >= 0 else f"{eval_cp / 100:.2f}"
    return "—"


def pv_str(fen: str, pv_json_str, max_moves: int = 6) -> str | None:
    """Format a stored pv_json string as a readable move sequence.

    Reconstructs move-number notation (e.g. '1. Nf3 d5 2. d4') using
    python-chess so the notation is correct for both white-to-move and
    black-to-move positions.  Returns None if pv_json_str is empty or
    unparseable, so callers can skip the line without an extra None check.
    """
    if not pv_json_str:
        return None
    try:
        pv = json.loads(pv_json_str)
    except Exception:
        return None
    board = chess.Board(fen)
    parts: list[str] = []
    for san in pv[:max_moves]:
        try:
            if board.turn == chess.WHITE:
                parts.append(f"{board.fullmove_number}. {san}")
            elif not parts:
                parts.append(f"{board.fullmove_number}… {san}")
            else:
                parts.append(san)
            board.push_san(san)
        except Exception:
            break
    return " ".join(parts) or None
